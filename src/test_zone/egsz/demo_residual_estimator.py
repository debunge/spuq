from __future__ import division
from functools import partial
import logging
import os

from spuq.application.egsz.pcg import pcg
from spuq.application.egsz.multi_operator import MultiOperator, PreconditioningOperator
from spuq.application.egsz.sample_problems import SampleProblem
from spuq.math_utils.multiindex import Multiindex
from spuq.math_utils.multiindex_set import MultiindexSet
from spuq.linalg.vector import inner
try:
    from dolfin import (Function, FunctionSpace, Constant, Mesh,
                        UnitSquare, refine, plot, interactive, solve, interpolate)
    from spuq.application.egsz.marking import Marking
    from spuq.application.egsz.residual_estimator import ResidualEstimator
    from spuq.application.egsz.fem_discretisation import FEMPoisson
    from spuq.fem.fenics.fenics_vector import FEniCSVector
except:
    print "FEniCS has to be available"
    os.sys.exit(1)

# ------------------------------------------------------------

# setup logging
# log level
LOG_LEVEL = logging.DEBUG
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(filename=__file__[:-2] + 'log', level=LOG_LEVEL,
                    format=log_format)
fenics_logger = logging.getLogger("FFC")
fenics_logger.setLevel(logging.WARNING)
fenics_logger = logging.getLogger("UFL")
fenics_logger.setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
logging.getLogger("spuq.application.egsz.multi_operator").disabled = True
#logging.getLogger("spuq.application.egsz.marking").setLevel(logging.INFO)
# add console logging output
ch = logging.StreamHandler()
ch.setLevel(LOG_LEVEL)
ch.setFormatter(logging.Formatter(log_format))
logger.addHandler(ch)
logging.getLogger("spuq").addHandler(ch)

# determine path of this module
path = os.path.dirname(__file__)
lshape_xml = os.path.join(path, 'lshape.xml')


# ------------------------------------------------------------

# some utility functions 

# setup initial multivector
def setup_vec(mesh, with_solve=True):
    fs = FunctionSpace(mesh, "CG", 1)
    vec = FEniCSVector(Function(fs))
    if with_solve:
        eval_poisson(vec)
    return vec

def eval_poisson(vec=None):
    if vec == None:
        vec = setup_vec(with_solve=False)
    fem_A = FEMPoisson.assemble_lhs(diffcoeff, vec.basis)
    fem_b = FEMPoisson.assemble_rhs(f, vec.basis)
    solve(fem_A, vec.coeffs, fem_b)
    return vec


# ============================================================
# PART A: Problem Setup
# ============================================================

# flag for final solution plotting
PLOT_MESHES = True
# flags for residual, projection, new mi refinement 
REFINEMENT = (True, True, True)

# define source term and diffusion coefficient
#f = Expression("10.*exp(-(pow(x[0] - 0.6, 2) + pow(x[1] - 0.4, 2)) / 0.02)", degree=3)
f = Constant("1.0")

# define initial multiindices
mis = [Multiindex(mis) for mis in MultiindexSet.createCompleteOrderSet(2, 1)]

# setup meshes 
mesh0 = refine(Mesh(lshape_xml))
mesh0 = UnitSquare(5, 5)
#meshes = SampleProblem.setupMeshes(mesh0, len(mis), {"refine":10, "random":(0.4, 0.3)})
meshes = SampleProblem.setupMeshes(mesh0, len(mis), {"refine":0})

zero_vec = partial(setup_vec, with_solve=False)
w = SampleProblem.setupMultiVector(dict([(mu, m) for mu, m in zip(mis, meshes)]), zero_vec)
logger.info("active indices of after initialisation: %s", w.active_indices())

# define coefficient field
coeff_field = SampleProblem.setupCF("EF-square")
a0, _ = coeff_field[0]

# define multioperator
A = MultiOperator(coeff_field, FEMPoisson.assemble_operator)


# ============================================================
# PART B: Adaptive Algorithm
# ============================================================

# refinement loop
# ===============
# error constants
gamma = 0.9
cQ = 1.0
ceta = 1.0
# marking parameters
theta_eta = 0.3
theta_zeta = 0.8
min_zeta = 1e-5
maxh = 1 / 10
theta_delta = 0.8
# solver
pcg_eps = 1e-3
pcg_maxiter = 100
error_eps = 1e-2
max_refinements = 3

for refinement in range(max_refinements):
    logger.info("*****************************")
    logger.info("REFINEMENT LOOP iteration %i", refinement + 1)
    logger.info("*****************************")

    # pcg solve
    # ---------
    b = 0 * w
    b0 = b[Multiindex()]
#    b0.coeffs = interpolate(f, b0._fefunc.function_space()).vector()
    b0.coeffs = FEMPoisson.assemble_rhs(f, b0.basis)
    P = PreconditioningOperator(a0, FEMPoisson.assemble_solve_operator)
    w, zeta, numit = pcg(A, b, P, w0=w, eps=pcg_eps, maxiter=pcg_maxiter)
    logger.info("PCG finished with zeta=%f after %i iterations", zeta, numit)
    b2 = A * w
    logger.info("Residual: %s", inner(b2 - b, b2 - b))

    # error evaluation
    # ----------------
    xi, resind, projind = ResidualEstimator.evaluateError(w, coeff_field, f, zeta, gamma, ceta, cQ, 1 / 10)
    if xi <= error_eps:
        logger.info("error reached requested accuracy, xi=%f", xi)
        break

    # marking
    # -------
    mesh_markers_R, mesh_markers_P, new_multiindices = Marking.mark(resind, projind, w, coeff_field, theta_eta, theta_zeta, theta_delta, min_zeta, maxh)
    if REFINEMENT[0]:
        mesh_markers = mesh_markers_R.copy()
    else:
        mesh_markers = {}
        logger.debug("SKIP residual refinement")
    if REFINEMENT[1]:
        mesh_markers.update(mesh_markers_P)
    else:
        logger.debug("SKIP projection refinement")
    if not REFINEMENT[2] or refinement == max_refinements:
        new_multiindices = {}
        logger.debug("SKIP new multiindex refinement")
    Marking.refine(w, mesh_markers, new_multiindices.keys(), partial(zero_vec, mesh=mesh0))
logger.info("ENDED refinement loop at refinement %i", refinement)


#b0 = b[Multiindex()]
#A0 = FEMPoisson.assemble_lhs(a0, b0.basis)
#w0 = A0 * b0
#w = 0 * w
#w[Multiindex()] = w0



# plot final meshes
if PLOT_MESHES:
    for mu, vec in w.iteritems():
        plot(vec.basis.mesh, title=str(mu), interactive=False, axes=True)
        vec.plot(title=str(mu), interactive=False)
#        b[mu].plot(title=str(mu), interactive=False)
#        break
    interactive()
