from abc import ABCMeta, abstractmethod

import numpy as np

from spuq.utils.decorators import copydocs
from spuq.utils.type_check import takes, anything, optional, sequence_of
from spuq.linalg.basis import FunctionBasis
from spuq.math_utils.multiindex_set import MultiindexSet

@copydocs
class StochasticBasis(FunctionBasis):
    __metaclass__ = ABCMeta

    @abstractmethod
    def sample(self, n):
        """Sample from the underlying distribution(s) and evaluate at
        basis functions"""
        raise NotImplementedError


class MultiindexBasis(StochasticBasis):
    @takes(anything, MultiindexSet, sequence_of(StochasticBasis))
    def __init__(self, I, bases):
        assert(I.m == len(bases))
        self.I = I
        self.bases = bases
        # assert bases are instances of StochasticBasis
        # assert dim of bases larger or equal to max in I
        for k, B in enumerate(bases):
            assert I.arr[:, k].max() < B.dim

    def sample(self, n):
        S = np.ones((self.I.count, n))
        for i, rv in enumerate(self.rvs):
            theta = rv.sample(n)
            Phi = rv.getOrthogonalPolynomials()
            Q = np.zeros((self.I.p + 1, n))
            for q in xrange(self.I.p + 1):
                Q[q, :] = Phi.eval(q, theta)
            S = S * Q[self.I.arr[:, i], :]
        return S

    @property
    def gramian(self):
        raise NotImplementedError

    @property
    def dim(self):
        raise NotImplementedError


class GPCBasis(StochasticBasis):
    def __init__(self, rv, p, **kwargs):
        StochasticBasis.__init__(self, **kwargs)
        self._rv = rv
        self._p = p

    def copy(self):
        return self.__cls__(self._rv, self._p, dual=self._dual)

    @property
    def rv(self):
        return self._rv

    @property
    def degree(self):
        return self._p

    @property
    def dim(self):
        return self._p + 1

    @property
    def domain_dim(self):
        return 1

    def eval(self, x):
        Phi = self._rv.orth_polys
        return Phi.eval(self._p, x, all_degrees=True)

    @property
    def gramian(self):
        # return DiagonalMatrix( [rv.orthpoly.norm(q) for q in xrange(p+1)])
        raise NotImplementedError

    def sample(self, n):
        rv = self._rv
        p = self._p
        theta = rv.sample(n)
        Phi = rv.orth_polys
        Q = np.zeros((p + 1, n))
        for q in xrange(p + 1):
            Q[q, :] = Phi.eval(q, theta)
        return Q
