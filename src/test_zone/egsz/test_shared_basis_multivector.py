# ===================================================================================
# EGSZ2a test: MultiVector with shared basis (FunctionSpace)
# adding new indices, refinement of basis and successive prolongation
# ===================================================================================

from __future__ import division
import os

from spuq.fem.fenics.fenics_vector import FEniCSVector
from spuq.application.egsz.multi_vector import MultiVectorSharedBasis
from spuq.math_utils.multiindex import Multiindex
from spuq.math_utils.multiindex_set import MultiindexSet

try:
    from dolfin import (FunctionSpace, UnitSquareMesh, Expression, interpolate, plot, interactive)
except Exception, e:
    import traceback
    print traceback.format_exc()
    print "FEniCS has to be available"
    os.sys.exit(1)

def initialise_multivector(mv, M):
    # initial multiindices
    mis = [Multiindex(mis) for mis in MultiindexSet.createCompleteOrderSet(M, 1)]
    # intialise fem vectors
    N = 15
    mesh = UnitSquareMesh(N, N)
    V = FunctionSpace(mesh, 'CG', 1)
    ex = Expression('sin(2*pi*A*x[0])', A=0)
    for i, mi in enumerate(mis):
        ex.A = i+1
        f = interpolate(ex, V)
        mv[mi] = FEniCSVector(f)

mv = MultiVectorSharedBasis()
initialise_multivector(mv, 2)
mv[Multiindex([2])] = mv.basis.basis.new_vector()
mv.refine()

for mi in mv.active_indices():
    plot(mv[mi]._fefunc)
interactive()
