from __future__ import division
from functools import partial
from collections import defaultdict
from math import sqrt
import logging
import os

from spuq.application.egsz.pcg import pcg
from spuq.application.egsz.multi_operator2 import MultiOperator, PreconditioningOperator
from spuq.application.egsz.coefficient_field import CoefficientField
from spuq.application.egsz.fem_discretisation import FEMDiscretisation
from spuq.application.egsz.multi_vector import MultiVector
from spuq.math_utils.multiindex import Multiindex
from spuq.utils.type_check import takes, anything
from spuq.utils.timing import timing

try:
    from dolfin import (Function, FunctionSpace, cells, Constant, refine)
    from spuq.application.egsz.marking2 import Marking
    from spuq.application.egsz.residual_estimator2 import ResidualEstimator
    from spuq.fem.fenics.fenics_utils import error_norm
except:
    import traceback
    print traceback.format_exc()
    print "FEniCS has to be available"
    os.sys.exit(1)

# ------------------------------------------------------------

# retrieve logger
logger = logging.getLogger(__name__)


# ============================================================
# PART A: PCG Solver
# ============================================================

def prepare_rhs(A, w, coeff_field, pde):
    b = 0 * w
    zero = Multiindex()
    b[zero].coeffs = pde.assemble_rhs(coeff_field.mean_func, basis=b[zero].basis, withNeumannBC=True)
    
    f = pde._f
    if f.value_rank() == 0:
        zero_func = Constant(0.0)
    else:
        zero_func = Constant((0.0,) * f.value_size())

    for m in range(w.max_order):
        eps_m = zero.inc(m)
        am_f, am_rv = coeff_field[m]
        beta = am_rv.orth_polys.get_beta(0)

        if eps_m in b.active_indices():
            g0 = b[eps_m].copy()
            g0.coeffs = pde.assemble_rhs(am_f, basis=b[eps_m].basis, withNeumannBC=False, f=zero_func)  # this equates to homogeneous Neumann bc
            pde.set_dirichlet_bc_entries(g0, homogeneous=True)
            b[eps_m] += beta[1] * g0

        g0 = b[zero].copy()
        g0.coeffs = pde.assemble_rhs(am_f, basis=b[zero].basis, f=zero_func)
        pde.set_dirichlet_bc_entries(g0, homogeneous=True)
        b[zero] += beta[0] * g0
    return b


def pcg_solve(A, w, coeff_field, pde, stats, pcg_eps, pcg_maxiter):
    b = prepare_rhs(A, w, coeff_field, pde)
    P = PreconditioningOperator(coeff_field.mean_func,
                                pde.assemble_solve_operator)

    w, zeta, numit = pcg(A, b, P, w0=w, eps=pcg_eps, maxiter=pcg_maxiter)
    logger.info("PCG finished with zeta=%f after %i iterations", zeta, numit)

    b2 = A * w
    stats["ERROR-L2"] = error_norm(b, b2, "L2")
    stats["ERROR-H1A"] = error_norm(b, b2, pde.norm)
    stats["DOFS"] = sum([b[mu]._fefunc.function_space().dim() for mu in b.keys()])
    stats["CELLS"] = sum([b[mu]._fefunc.function_space().mesh().num_cells() for mu in b.keys()])
    logger.info("Residual = [%s (L2)] [%s (H1)] with [%s dofs] and [%s cells]", stats["ERROR-L2"], stats["ERROR-H1A"], stats["DOFS"], stats["CELLS"])
    return w, zeta


# ============================================================
# PART B: Adaptive Algorithm
# ============================================================

@takes(MultiOperator, CoefficientField, FEMDiscretisation, list, MultiVector, anything, int)
def AdaptiveSolver(A, coeff_field, pde,
                    mis, w0, mesh0, degree,
                    # marking parameters
                    rho=1.0, # tail factor
                    sigma=1.0, # residual factor
                    theta_x=0.4, # residual marking bulk parameter
                    theta_y=0.4, # tail bound marking bulk paramter
                    maxh=0.1, # maximal mesh width for coefficient maximum norm evaluation
                    add_maxm=20, # maximal search length for new new multiindices (to be added to max order of solution w)
                    # residual error
                    quadrature_degree= -1,
                    # pcg solver
                    pcg_eps=1e-6,
                    pcg_maxiter=100,
                    # adaptive algorithm threshold
                    error_eps=1e-2,
                    # refinements
                    max_refinements=5,
                    max_inner_refinements=20, # max iterations for inner residual refinement loop
                    do_refinement={"RES":True, "TAIL":True},
                    do_uniform_refinement=False,
                    w_history=None,
                    sim_stats=None):
    
    # define store function for timings
    def _store_stats(val, key, stats):
        stats[key] = val
    
    # get rhs
    f = pde.f

    # setup w and statistics
    w = w0
    if sim_stats is None:
        assert w_history is None or len(w_history) == 0
        sim_stats = []

    try:
        start_iteration = max(len(sim_stats) - 1, 0)
    except:
        start_iteration = 0
    logger.info("START/CONTINUE EXPERIMENT at iteration %i", start_iteration)

    # data collection
    import resource
    refinement = None
    for refinement in range(start_iteration, max_refinements + 1):
        logger.info("************* REFINEMENT LOOP iteration %i (of %i) *************", refinement, max_refinements)
        # memory usage info
        logger.info("\n======================================\nMEMORY USED: " + str(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) + "\n======================================\n")

        # ---------
        # pcg solve
        # ---------
        
        stats = {}
        with timing(msg="pcg_solve", logfunc=logger.info, store_func=partial(_store_stats, key="TIME-PCG", stats=stats)):
            w, zeta = pcg_solve(A, w, coeff_field, pde, stats, pcg_eps, pcg_maxiter)

        logger.info("DIM of w = %s", w.dim)
        if w_history is not None and (refinement == 0 or start_iteration < refinement):
            w_history.append(w)

        # -------------------
        # evaluate estimators
        # -------------------
        
        # evaluate estimate_y
        logger.debug("evaluating upper tail bound")
        with timing(msg="ResidualEstimator.evaluateUpperTailBound", logfunc=logger.info, store_func=partial(_store_stats, key="TIME-TAIL", stats=stats)):
            global_zeta, zeta, zeta_bar, eval_zeta_m = ResidualEstimator.evaluateUpperTailBound(w, coeff_field, pde, maxh, add_maxm)
            
        # evaluate estimate_x
        with timing(msg="ResidualEstimator.evaluateResidualEstimator", logfunc=logger.info, store_func=partial(_store_stats, key="TIME-RES", stats=stats)):
            global_eta, eta, eta_local = ResidualEstimator.evaluateResidualEstimator(w, coeff_field, pde, f, quadrature_degree)
            
        # set overall error
        xi = sqrt(global_eta ** 2 + global_zeta ** 2)
        logger.info("Overall Estimator Error xi = %s while residual error is %s and tail error is %s", xi, global_eta, global_zeta)

        # store simulation data
        stats["ERROR-EST"] = xi
        stats["ERROR-RES"] = global_eta
        stats["ERROR-TAIL"] = global_zeta
        stats["MARKING-RES"] = 0
        stats["MARKING-MI"] = 0
        stats["TIME-MARK-RES"] = 0
        stats["TIME-REFINE-RES"] = 0
        stats["TIME-MARK-TAIL"] = 0
        stats["TIME-REFINE-TAIL"] = 0
        stats["MI"] = [mu for mu in w.active_indices()]
        stats["DIM"] = w.dim
        if refinement == 0 or start_iteration < refinement:
            sim_stats.append(stats)
            print "SIM_STATS:", sim_stats[refinement]
            
        # exit when either error threshold or max_refinements is reached
        if refinement > max_refinements:
            logger.info("skipping refinement after final solution in iteration %i", refinement)
            break
        if xi <= error_eps:
            logger.info("error reached requested accuracy, xi=%f", xi)
            break 

        # -----------------------------------
        # mark and refine and activate new mi
        # -----------------------------------

        if refinement < max_refinements:
            logger.debug("START marking")
            # === mark x ===
            if do_refinement["RES"]:
                cell_ids = []
                logger.info("REFINE RES")
                if not do_uniform_refinement:        
                    if global_eta > rho * global_zeta:
                        with timing(msg="Marking.mark_x", logfunc=logger.info, store_func=partial(_store_stats, key="TIME-MARK-RES", stats=stats)):
                            cell_ids = Marking.mark_x(eta, eta_local, theta_x)
                else:
                    # uniformly refine mesh
                    logger.info("UNIFORM refinement")
                    cell_ids = [c.index() for c in cells(w.basis._fefs.mesh())]
            else:
                logger.info("SKIP residual refinement")
            # refine mesh
            logger.debug("w.dim BEFORE refinement: %f", w.dim)
            with timing(msg="Marking.refine_x", logfunc=logger.info, store_func=partial(_store_stats, key="TIME-REFINE-RES", stats=stats)):
                w = Marking.refine_x(w, cell_ids)
            logger.debug("w.dim AFTER refinement: %f", w.dim)
                            
            # === mark y ===
            if do_refinement["TAIL"]:
                logger.info("REFINE TAIL")
                with timing(msg="Marking.mark_y", logfunc=logger.info, store_func=partial(_store_stats, key="TIME-MARK-TAIL", stats=stats)):
                    new_mi = Marking.mark_y(global_zeta, zeta, zeta_bar, eval_zeta_m, theta_y)
            else:
                new_mi = []
                logger.info("SKIP tail refinement")
            # add new multiindices
            with timing(msg="Marking.refine_y", logfunc=logger.info, store_func=partial(_store_stats, key="TIME-REFINE-TAIL", stats=stats)):
                Marking.refine_y(w, new_mi, partial(setup_vector, pde=pde, basis=w.basis))

            # === uniformly refine for coefficient function oscillations ===
            if do_refinement["OSC"]:
                logger.info("REFINE OSC")
                with timing(msg="Marking.refine_osc", logfunc=logger.info, store_func=partial(_store_stats, key="TIME-REFINE-OSC", stats=stats)):
                    osc_refinements = Marking.refine_osc(w, coeff, M)
            else:
                logger.info("SKIP tail refinement")
            # add new multiindices
            with timing(msg="Marking.refine_y", logfunc=logger.info, store_func=partial(_store_stats, key="TIME-REFINE-TAIL", stats=stats)):
                Marking.refine_y(w, new_mi, partial(setup_vector, pde=pde, basis=w.basis))

            
            logger.info("MARKING was carried out with %s (res) cells and %s (mi) new multiindices", len(mesh_markers), len(new_mi))
            stats["MARKING-RES"] = len(mesh_markers)
            stats["MARKING-MI"] = len(new_mi)
    
    if refinement:
        logger.info("ENDED refinement loop after %i of %i refinements with %i dofs and %i active multiindices",
                    refinement, max_refinements, sim_stats[refinement]["DOFS"], len(sim_stats[refinement]["MI"]))

    return w, sim_stats
