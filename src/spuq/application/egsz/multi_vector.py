from __future__ import division

from spuq.fem.fenics.fenics_vector import FEniCSVector
from spuq.linalg.vector import Scalar, Vector, FlatVector, inner
from spuq.linalg.basis import Basis
from spuq.linalg.operator import BaseOperator
from spuq.math_utils.multiindex import Multiindex
from spuq.math_utils.multiindex_set import MultiindexSet
from spuq.utils.type_check import takes, anything, optional
from spuq.utils import strclass

import numpy as np
import os
import pickle
from collections import defaultdict

__all__ = ["MultiVector", "MultiVectorWithProjection", "MultiVectorSharedBasis"]

import logging
logger = logging.getLogger(__name__)


# support for set of multiindices
def supp(Lambda):
    s = [set(mu.supp) for mu in Lambda]
    return set.union(*s)


class MultiVector(Vector):
    """Accommodates tuples of type (MultiindexSet, Vector/Object).
    
    This class manages a set of Vectors associated to MultiindexSet instances.
    A Vector contains a coefficient vector and the respespective basis.
    Note that the type of the second value of the tuple is not restricted to
    anything specific."""

    @takes(anything, optional(callable))
    def __init__(self, on_modify=lambda: None, multivector=None):
        self.mi2vec = dict()
        self.on_modify = on_modify
        if multivector is not None:
            for mu, vec in multivector.iteritems():
                self[mu] = vec

    @property
    def basis(self):  # pragma: no cover
        """Return basis for MultiVector"""
        return MultiVectorBasis(self)

    @property
    def dim(self, summed=False):
        """Return set of dimensions of MultiVector."""
        if summed:
            return sum(d for d in self.dim.values())
        else:
            return {mu:self[mu].dim for mu in self.active_indices()}

    def flatten(self):
        """Return flattened (Euclidian) vector."""
        F = self.to_euclidian_operator
        return F.apply(self)

    @property
    def to_euclidian_operator(self):
        return MultiVectorOperator(self, to_euclidian=True)

    @property
    def from_euclidian_operator(self):
        return MultiVectorOperator(self, to_euclidian=False)

    @property
    def max_order(self):
        """Returns the maximum order of the multiindices."""
        return max(len(mu) for mu in self.keys())

    @takes(anything, Multiindex)
    def __getitem__(self, mi):
        return self.mi2vec[mi]

    @takes(anything, Multiindex, Vector)
    def __setitem__(self, mi, val):
        self.on_modify()
        self.mi2vec[mi] = val

    def __len__(self):
        return len(self.mi2vec)

    def keys(self):
        return self.mi2vec.keys()

    def values(self):
        return self.mi2vec.values()

    def iteritems(self):
        return self.mi2vec.iteritems()

    def active_indices(self):
        return sorted(self.keys())

    def copy(self):
        mv = self.__class__()
        for mi in self.keys():
            mv[mi] = self[mi].copy()
        return mv

    @takes(anything, MultiindexSet, Vector)
    def set_defaults(self, multiindex_set, init_vector):
        self.on_modify()
        for mi in multiindex_set:
            self[Multiindex(mi)] = init_vector.copy()

    def set_zero(self):
        for mu in self.active_indices():
            self[mu].set_zero()

    def __eq__(self, other):
        return (type(self) == type(other) and
                self.mi2vec == other.mi2vec)

    def __neg__(self):
        new = self.copy()
        for mi in self.active_indices():
            new[mi] = -self[mi]
        return new

    def __iadd__(self, other):
        assert self.active_indices() == other.active_indices()
        self.on_modify()
        for mi in self.active_indices():
            self[mi] += other[mi]
        return self

    def __isub__(self, other):
        assert self.active_indices() == other.active_indices()
        self.on_modify()
        for mi in self.active_indices():
            self[mi] -= other[mi]
        return self

    def __imul__(self, other):
        assert isinstance(other, Scalar)
        self.on_modify()
        for mi in self.keys():
            self[mi] *= other
        return self

    def __inner__(self, other):
        assert isinstance(other, MultiVector)
        s = 0.0
        for mi in self.keys():
            s += inner(self[mi], other[mi])
        return s

    def __repr__(self):
        return "<%s keys=%s>" % (strclass(self.__class__), self.mi2vec.keys())

    def __getstate__(self):
        # pickling preparation
        odict = self.__dict__.copy() # copy the dict since we change it
        del odict['on_modify']
        return odict
    
    def __setstate__(self, d):
        # pickling restore
        self.__dict__.update(d)
    

class MultiVectorWithProjection(MultiVector):
    @takes(anything, optional(callable), optional(bool))
    def __init__(self, project=None, cache_active=False, multivector=None):
        if not project:
            project = MultiVectorWithProjection.default_project
        self.project = project
        self._proj_cache = defaultdict(dict)
        self._back_cache = {}
        self._cache_active = cache_active
        MultiVector.__init__(self, self.clear_cache, multivector=multivector)

    @staticmethod
    def default_project(vec_src, dest):
        """Project the source vector onto the basis of the destination vector."""
        if not isinstance(dest, Basis):
            basis = dest.basis
        else:
            basis = dest
        assert hasattr(basis, "project_onto")
        return basis.project_onto(vec_src)

    def copy(self):
        mv = MultiVector.copy(self)
        mv.project = self.project
        return mv

    def __eq__(self, other):
        return (MultiVector.__eq__(self, other) and
                self.project == other.project)

    def clear_cache(self):
        self._back_cache.clear()
        self._proj_cache.clear()

    @takes(anything, Multiindex, Multiindex, anything)
    def get_projection(self, mu_src, mu_dest, degree=None):
        """Return projection of vector in multivector"""
        if degree is None:
            degree = self[mu_dest].degree
        # w/o caching
        if not self._cache_active:
            if self[mu_dest].degree == degree:
                return self.project(self[mu_src], self[mu_dest])
            else:
                V = self[mu_dest].basis.copy(degree)
                return V.project_onto(self[mu_src])
        
        # with caching
        args = (mu_src, mu_dest, self.project)
        vec = self._proj_cache[degree].get(args)            # check cache
        #        print "P MultiVector get_projection", mu_src, mu_dest
        if not vec:
        #            print "P ADDING TO CACHE: new projection required..."
            if self[mu_dest].degree == degree:
                vec = self.project(self[mu_src], self[mu_dest])
            else:
                try:
                    V = self._proj_cache[degree]["V"]       # try to retrieve basis
                except:
                    V = self[mu_dest].basis.copy(degree)    # create and store basis if necessary
                    self._proj_cache[degree]["V"] = V
                vec = V.project_onto(self[mu_src])
            self._proj_cache[degree][args] = vec
            #            print "P proj_cache size", len(self._proj_cache)
        #            print "P with keys", self._proj_cache.keys()
        #        else:
        #            print "P CACHED!"
        #        print "P dim mu_src =", self[mu_src].coeffs.size()
        #        print "P dim mu_dest =", self[mu_dest].coeffs.size()
        #        print "P dim vec =", vec.coeffs.size()
        return vec

    @takes(anything, Multiindex, Multiindex)
    def get_back_projection(self, mu_src, mu_dest):
        """Return back projection of vector in multivector"""
        # w/o caching
        if not self._cache_active:
            vec_prj = self.get_projection(mu_src, mu_dest)
            return self.project(vec_prj, self[mu_src])

        # with caching
        args = (mu_src, mu_dest, self.project)
        vec = self._back_cache.get(args)
        #        print "BP MultiVector get_back_projection", mu_src, mu_dest
        if not vec:
        #            print "BP ADDING TO CACHE: new back_projection required..."
            vec_prj = self.get_projection(mu_src, mu_dest)
            vec = self.project(vec_prj, self[mu_src])
            self._back_cache[args] = vec
            #            print "BP back_cache size", len(self._back_cache)
        #            print "BP with keys", self._back_cache.keys()
        #        else:
        #            print "BP CACHED!"
        #        print "BP dim mu_src =", self[mu_src].coeffs.size()
        #        print "BP dim mu_dest =", self[mu_dest].coeffs.size()
        #        print "BP dim vec =", vec.coeffs.size()
        return vec

    @takes(anything, Multiindex, Multiindex, int, bool)
    def get_projection_error_function(self, mu_src, mu_dest, reference_degree, refine_mesh=0):
        """Construct projection error function by projecting mu_src vector to mu_dest space of dest_degree.
        From this, the projection of mu_src onto the mu_dest space, then to the mu_dest space of dest_degree is subtracted.
        If refine_mesh > 0, the destination mesh is refined uniformly n times."""
        from spuq.fem.fenics.fenics_utils import create_joint_mesh
        from dolfin import FunctionSpace, VectorFunctionSpace
        from spuq.fem.fenics.fenics_basis import FEniCSBasis
        
        # get joint mesh based on destination space
        basis_src = self[mu_src].basis 
        basis_dest = self[mu_dest].basis
        mesh_reference, parents = create_joint_mesh([basis_src.mesh], basis_dest.mesh)

        # create function space on destination mesh        
        if basis_dest._fefs.num_sub_spaces() > 0:
            fs_reference = VectorFunctionSpace(mesh_reference, basis_dest._fefs.ufl_element().family(), reference_degree)
        else:
            fs_reference = FunctionSpace(mesh_reference, basis_dest._fefs.ufl_element().family(), reference_degree)
        basis_reference = FEniCSBasis(fs_reference, basis_dest._ptype)
        
        # project both vectors to reference space
        w_reference = basis_reference.project_onto(self[mu_src])
        w_dest = self.get_projection(mu_src, mu_dest)
        w_dest = basis_reference.project_onto(w_dest)
        
        # define summation function to get values on original destination mesh from function space on joint mesh
        def sum_up(vals):
            sum_vals = [sum(vals[v]) for _, v in parents.iteritems()]
            return np.array(sum_vals)
        return w_dest - w_reference, sum_up

    @takes(anything, Multiindex, Multiindex, int, bool)
    def get_projection_error_function_old(self, mu_src, mu_dest, reference_degree, refine_mesh=0):
        """Construct projection error function by projecting mu_src vector to mu_dest space of dest_degree.
        From this, the projection of mu_src onto the mu_dest space, then to the mu_dest space of dest_degree is subtracted.
        If refine_mesh > 0, the destination mesh is refined uniformly n times."""
        # TODO: If refine_mesh is True, the destination space of mu_dest is ensured to include the space of mu_src by mesh refinement
        # TODO: proper description
        # TODO: separation of fenics specific code
        from dolfin import refine, FunctionSpace, VectorFunctionSpace
        from spuq.fem.fenics.fenics_basis import FEniCSBasis
        if not refine_mesh:
            w_reference = self.get_projection(mu_src, mu_dest, reference_degree)
            w_dest = self.get_projection(mu_src, mu_dest)
            w_dest = w_reference.basis.project_onto(w_dest)
            sum_up = lambda vals: vals
        else:
            # uniformly refine destination mesh
            # NOTE: the cell_marker based refinement used in FEniCSBasis is a bisection of elements
            # while refine(mesh) carries out a red-refinement of all cells (split into 4)
#            basis_src = self[mu_src].basis
            basis_dest = self[mu_dest].basis
            mesh_reference = basis_dest.mesh
            for _ in range(refine_mesh):
                mesh_reference = refine(mesh_reference)
#            print "multi_vector::get_projection_error_function"
#            print type(basis_src._fefs), type(basis_dest._fefs)
#            print basis_src._fefs.num_sub_spaces(), basis_dest._fefs.num_sub_spaces()
#            if isinstance(basis_dest, VectorFunctionSpace):
            if basis_dest._fefs.num_sub_spaces() > 0:
                fs_reference = VectorFunctionSpace(mesh_reference, basis_dest._fefs.ufl_element().family(), reference_degree)
            else:
                fs_reference = FunctionSpace(mesh_reference, basis_dest._fefs.ufl_element().family(), reference_degree)
            basis_reference = FEniCSBasis(fs_reference, basis_dest._ptype)
            # project both vectors to reference space
            w_reference = basis_reference.project_onto(self[mu_src])
            w_dest = self.get_projection(mu_src, mu_dest)
            w_dest = basis_reference.project_onto(w_dest)
            sum_up = lambda vals: np.array([sum(vals[i * 4:(i + 1) * 4]) for i in range(len(vals) / 4 ** refine_mesh)])
        return w_dest - w_reference, sum_up

    @property
    def cache_active(self):
        return self._cache_active
    
    @cache_active.setter
    def cache_active(self, val):
        self._cache_active = val
        if not val:
            self.clear_cache()

    def __getstate__(self):
        # pickling preparation
        odict = self.__dict__.copy() # copy the dict since we change it
        odict['_proj_cache'] = defaultdict(dict)
        odict['_back_cache'] = {}
        del odict['on_modify']
        del odict['project']
        return odict
    
    def __setstate__(self, d):
        # pickling restore
        self.__dict__.update(d)
        # NOTE: this sets default projection and does not restore any other projection type! 
        self.project = MultiVectorWithProjection.default_project


class MultiVectorOperator(BaseOperator):
    def __init__(self, multvec=None, to_euclidian=True, basis=None):
#        super(MultiVectorOperator, self).__init__(None, None)
        if multvec is not None:
            self._basis = multvec.basis
        else:
            assert basis is not None
            self._basis = basis
        self._dim = self._basis.dim
        self._dimsum = sum(self._dim.values())      # ;)
        self._to_euclidian = to_euclidian
        self._last_vec = None
        
    @property
    def dim(self):
        return self._dimsum

    @property
    def can_invert(self):
        return True 

    def invert(self):
        return MultiVectorOperator(to_euclidian=False, basis=self._basis)

    def _multivec_to_euclidian(self, vec):
        assert vec.dim == self._dim
        if not self._last_vec:
            new_vec = FlatVector(np.empty(self._dimsum))
            self._last_vec = new_vec
        else:
            new_vec = self._last_vec
        coeffs = new_vec.coeffs

        start = 0
        for mu in self._basis.active_indices():
            vec_mu = vec[mu]
            dim = vec_mu.dim
            coeffs[start:start + dim] = vec_mu.coeffs.array()
            start += dim
        return new_vec

    def _euclidian_to_multivec(self, vec):
        assert vec.dim == self._dimsum

        if not self._last_vec:
            new_vec = MultiVector()
            for mu in self._basis.active_indices():
                vec_mu = FEniCSVector.from_basis(self._basis._basis[mu])
                new_vec[mu] = vec_mu
            self._last_vec = new_vec
        else:
            new_vec = self._last_vec

        start = 0
        basis = self._basis
        for mu in basis.active_indices():
            vec_mu = new_vec[mu]
            dim = basis._basis[mu].dim
            vec_mu.coeffs = vec.coeffs[start:start + dim]
            new_vec[mu] = vec_mu
            start += dim
        return new_vec

    def apply(self, vec):
        if self._to_euclidian:
            return self._multivec_to_euclidian(vec)
        else:
            return self._euclidian_to_multivec(vec)


class MultiVectorSharedBasis(MultiVector):
    """Specialisation of MultiVector which only allows a shared basis between all multiindices."""

    @takes(anything, optional(callable))
    def __init__(self, on_modify=lambda: None, multivector=None):
        self.single_basis = True    # TODO: flag for pickling
        self.mi2vec = dict()
        self.on_modify = on_modify
        if multivector is not None:
            for mu, vec in multivector.iteritems():
                self[mu] = vec
                assert self[mu].basis == self[self.active_indices()[0]]

    @property
    def basis(self):  # pragma: no cover
        """Return basis for MultiVector"""
        return MultiVectorBasis(self, single_basis=True)

    @takes(anything, Multiindex, Vector)
    def __setitem__(self, mi, val):
        self.on_modify()
        if len(self) > 0:
            assert val.basis == self[self.active_indices()[0]].basis
        self.mi2vec[mi] = val

    def keys(self):
        return self.mi2vec.keys()

    def iteritems(self):
        return self.mi2vec.iteritems()

    def active_indices(self):
        return sorted(self.keys())

    def copy(self):
        mv = self.__class__()
        for mi in self.keys():
            mv[mi] = self[mi].copy()
        return mv

    def refine(self, cell_ids=None):
        _, prolongate, _ = self.basis.basis.refine(cell_ids)
        mv = self.__class__()
        for mi in self.keys():
            mv[mi] = prolongate(self[mi])
        return mv

    def refine_maxh(self, maxh):
        new_basis, prolongate, _, num_cells_refined = self.basis.basis.refine_maxh(maxh)
        logger.info("refined {0} cells to achieve maxh {1}".format(num_cells_refined, maxh))
        mv = self.__class__()
        for mi in self.keys():
            mv[mi] = prolongate(self[mi])
        return mv

    def project(self, vec_src, dest):
        """Project the source vector onto the basis of the destination vector."""
        if not isinstance(dest, Basis):
            basis = dest.basis
        else:
            basis = dest
        assert hasattr(basis, "project_onto")
        return basis.project_onto(vec_src)
        
    @takes(anything, MultiindexSet, Vector)
    def set_defaults(self, multiindex_set, init_vector):
        self.on_modify()
        for mi in multiindex_set:
            self[Multiindex(mi)] = init_vector.copy()

    def __getstate__(self):
        # pickling preparation
        odict = self.__dict__.copy() # copy the dict since we change it
        del odict['on_modify']
        return odict
    
    def __setstate__(self, d):
        # pickling restore
        self.__dict__.update(d)


class MultiVectorBasis(object):
    def __init__(self, multivec, single_basis=False):
        self.single_basis = single_basis
        if self.single_basis:
            self.basis = multivec[multivec.active_indices()[0]].basis
        else:
            self.basis = { mu:multivec[mu].basis for mu in multivec.active_indices() }

    @property
    def dim(self):
        if self.single_basis:
            return self._basis.dim 
        else:
            return {mu:self._basis[mu].dim for mu in self._basis.keys()}

    def active_indices(self):
        return self._basis.keys()
