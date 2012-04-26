from __future__ import division
import logging
import os

from spuq.application.egsz.multi_operator import MultiOperator
from spuq.application.egsz.sample_problems import SampleProblem
from spuq.math_utils.multiindex import Multiindex
from spuq.math_utils.multiindex_set import MultiindexSet
try:
    from dolfin import (Function, FunctionSpace, Constant, UnitSquare, refine,
                            solve, plot, interactive, errornorm)
    from spuq.application.egsz.fem_discretisation import FEMPoisson
    from spuq.application.egsz.adaptive_solver import adaptive_solver
    from spuq.fem.fenics.fenics_vector import FEniCSVector
except Exception, e:
    import traceback
    print traceback.format_exc()
    print "FEniCS has to be available"
    os.sys.exit(1)

# ------------------------------------------------------------

# setup logging
# log level
LOG_LEVEL = logging.INFO
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

# utility functions 

# setup initial multivector
def setup_vec(mesh):
    fs = FunctionSpace(mesh, "CG", 1)
    vec = FEniCSVector(Function(fs))
    return vec


# ============================================================
# PART A: Problem Setup
# ============================================================

# flag for residual graph plotting
PLOT_RESIDUAL = True

# flag for final solution plotting
PLOT_MESHES = False

# flags for residual, projection, new mi refinement 
refinement = {"RES":True, "PROJ":True, "MI":False}
uniform_refinement = False

# define source term and diffusion coefficient
#f = Expression("10.*exp(-(pow(x[0] - 0.6, 2) + pow(x[1] - 0.4, 2)) / 0.02)", degree=3)
f = Constant("1.0")

# define initial multiindices
mis = [Multiindex(mis) for mis in MultiindexSet.createCompleteOrderSet(2, 2)]

# setup meshes
#mesh0 = refine(Mesh(lshape_xml))
mesh0 = UnitSquare(5, 5)
meshes = SampleProblem.setupMeshes(mesh0, len(mis), {"refine":0})

w0 = SampleProblem.setupMultiVector(dict([(mu, m) for mu, m in zip(mis, meshes)]), setup_vec)

logger.info("active indices of w after initialisation: %s", w0.active_indices())

# define coefficient field
coeff_field = SampleProblem.setupCF("EF-square", {"exp":4})

# define multioperator
A = MultiOperator(coeff_field, FEMPoisson.assemble_operator)


# ============================================================
# PART B: Adaptive Algorithm
# ============================================================

(w, info) = adaptive_solver(A, coeff_field, f, mis, w0, mesh0,
    do_refinement=refinement,
    do_uniform_refinement=uniform_refinement,
    max_refinements=1
)


# ============================================================
# PART C: Evaluation of Deterministic Solution and Comparison
# ============================================================

# dbg
print "w:", w

Delta = w.active_indices()
maxm = max(len(mu) for mu in Delta) + 1
RV_samples = [0, ]
for m in range(1, maxm):
    RV_samples.append(float(coeff_field[m][1].sample(1)))

sample_map = {}
def prod(l):
    p = 1
    for f in l:
        if p is None:
            p = f
        else:
            p *= f
    return p

for mu in Delta:
    sample_map[mu] = prod(coeff_field[m + 1][1].orth_polys[mu[m]](RV_samples[m + 1]) for m in range(len(mu)))

# dbg
print "RV_samples:", RV_samples
print "sample_map:", sample_map

# create reference mesh and function space
cf_mesh_refinements = 2
mesh = refine(mesh0)
for i in range(cf_mesh_refinements):
    mesh = refine(mesh)
fs = FunctionSpace(mesh, "CG", 1)

# ============== STOCHASTIC SOLUTION ==============

# sum up (stochastic) solution vector on reference function space wrt samples
sample_sol = None
vec = FEniCSVector(Function(fs))
for mu in Delta:
    sol = w.project(w[mu], vec) * sample_map[mu]
    if sample_sol is None:
        sample_sol = sol
    else:
        sample_sol += sol

# dbg
#C0 = sample_sol.coeffs
#fs0 = sample_sol.basis._fefs
#FS0 = FunctionSpace(fs0.mesh(), "CG", 1)
#F0 = Function(FS0, C0)
#F1 = Function(fs0, C0)
#plot(sample_sol.basis._fefs.mesh())
#plot(FS0.mesh())
#plot(F0)
#plot(F1)
#interactive()

# ============== DETERMINISTIC SOLUTION ==============

# sum up coefficient field sample
a0 = coeff_field[0][0]
a = a0
for m in range(1, maxm):
    a_m = RV_samples[m] * coeff_field[m][0]
    a += a_m

A = FEMPoisson.assemble_lhs(a, vec.basis)
b = FEMPoisson.assemble_rhs(Constant("1.0"), vec.basis)
X = 0 * b
solve(A, X, b)
sample_sol_det = FEniCSVector(Function(vec.basis._fefs, X))

# evaluate errors
print "ERRORS: L2 =", errornorm(sample_sol._fefunc, sample_sol_det._fefunc, "L2"), \
            "  H1 =", errornorm(sample_sol._fefunc, sample_sol_det._fefunc, "H1") 
sample_sol_err = sample_sol - sample_sol_det
sample_sol_err.coeffs = sample_sol_err.coeffs
sample_sol_err.coeffs.abs()

# plotting
sample_sol.plot(interactive=False, title="stochastic solution")
sample_sol_det.plot(interactive=False, title="deterministic solution")
sample_sol_err.plot(interactive=True, title="error")
