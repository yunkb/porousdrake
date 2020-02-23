from firedrake import *
import numpy as np
from firedrake.petsc import PETSc
from firedrake import COMM_WORLD
import convergence.exact_solution as exact_solution
from convergence.model_parameters import *

try:
    import matplotlib.pyplot as plt

    plt.rcParams["contour.corner_mask"] = False
    plt.close("all")
except:
    warning("Matplotlib not imported")


def sdhm(
    mesh,
    degree,
    beta_0=Constant(1e-2),
    delta_0=Constant(1.0),
    delta_1=Constant(-0.5),
    delta_2=Constant(0.5),
    delta_3=Constant(0.5),
    mesh_parameter=True,
    solver_parameters={},
):
    if not solver_parameters:
        solver_parameters = {
            "snes_type": "ksponly",
            "mat_type": "matfree",
            "pmat_type": "matfree",
            "ksp_type": "preonly",
            "pc_type": "python",
            # Use the static condensation PC for hybridized problems
            # and use a direct solve on the reduced system for lambda_h
            "pc_python_type": "firedrake.SCPC",
            "pc_sc_eliminate_fields": "0, 1",
            "condensed_field": {
                "ksp_type": "preonly",
                "pc_type": "lu",
                "pc_factor_mat_solver_type": "mumps",
            },
        }

    pressure_family = "DG"
    velocity_family = "DG"
    trace_family = "HDiv Trace"
    U = VectorFunctionSpace(mesh, velocity_family, degree)
    V = FunctionSpace(mesh, pressure_family, degree)
    T = FunctionSpace(mesh, trace_family, degree)
    W = U * V * T

    # Trial and test functions
    DPP_solution = Function(W)
    u, p, lambda_h = split(DPP_solution)
    v, q, mu_h = TestFunctions(W)

    # Mesh entities
    n = FacetNormal(mesh)
    h = CellDiameter(mesh)

    # Exact solution and source term projection
    p_e, v_e, f = decompose_exact_solution(mesh, degree)

    # Boundary conditions
    bcs = DirichletBC(W.sub(1), Constant(0.0), "on_boundary", method="geometric")

    # Stabilizing parameter
    beta = beta_0 / h
    beta_avg = beta_0 / h("+")
    # beta = beta_0
    # beta_avg = beta_0
    if mesh_parameter:
        delta_2 = delta_2 * h * h
        delta_3 = delta_3 * h * h

    # Mixed classical terms
    a = (dot(alpha() * u, v) - div(v) * p - delta_0 * q * div(u)) * dx
    L = -delta_0 * f * q * dx - delta_0 * dot(rhob, v) * dx
    # Stabilizing terms
    ###
    a += delta_1 * inner(invalpha() * (alpha() * u + grad(p)), delta_0 * alpha() * v + grad(q)) * dx
    ###
    a += delta_2 * alpha() * div(u) * div(v) * dx
    L += delta_2 * alpha() * f * div(v) * dx
    ###
    a += delta_3 * inner(invalpha() * curl(alpha() * u), curl(alpha() * v)) * dx
    # Hybridization terms
    ###
    a += lambda_h("+") * jump(v, n) * dS + mu_h("+") * jump(u, n) * dS
    ###
    a += beta_avg * invalpha()("+") * (p("+") - lambda_h("+")) * (q("+") - mu_h("+")) * dS
    # Weakly imposed BC from hybridization
    a += beta * invalpha() * (lambda_h - p_e) * mu_h * ds  # right one
    # a += beta * invalpha() * (lambda_h - p_e) * (mu_h - q) * ds
    # a += beta * invalpha() * (p_e - lambda_h) * (q - mu_h) * ds
    # a += ((p_e - lambda_h) * dot(v, n) + mu_h * (dot(u, n) - dot(v_e, n))) * ds
    # a += (p_e * dot(v, n) + mu_h * (dot(u, n) - dot(v_e, n))) * ds
    a += (p_e * dot(v, n) + mu_h * dot(u, n)) * ds  # right one
    # a += ((p_e - lambda_h) * dot(v, n) + mu_h * dot(u, n)) * ds
    # a += (lambda_h * dot(v, n) + mu_h * dot(u, n)) * ds

    F = a - L

    #  Solving SC below
    PETSc.Sys.Print(
        "*******************************************\nSolving using static condensation.\n"
    )
    problem_flow = NonlinearVariationalProblem(F, DPP_solution)
    # solver_flow = NonlinearVariationalSolver(problem_flow, solver_parameters=solver_parameters)
    solver_flow = NonlinearVariationalSolver(
        problem_flow, solver_parameters=solver_parameters, bcs=bcs
    )
    solver_flow.solve()

    # Returning numerical and exact solutions
    p_sol, v_sol = _decompose_numerical_solution_hybrid(DPP_solution)
    return p_sol, v_sol, p_e, v_e


def lsh(
    mesh,
    degree,
    beta_0=Constant(0),
    delta_1=Constant(1),
    delta_2=Constant(1),
    delta_3=Constant(1),
    stabilizing_mass_constant=Constant(0),
    ls_lambda_constant=Constant(0),
    mesh_parameter=True,
    solver_parameters={},
):
    if not solver_parameters:
        solver_parameters = {
            "snes_type": "ksponly",
            "mat_type": "matfree",
            "pmat_type": "matfree",
            "ksp_type": "preonly",
            "pc_type": "python",
            # Use the static condensation PC for hybridized problems
            # and use a direct solve on the reduced system for lambda_h
            "pc_python_type": "firedrake.SCPC",
            "pc_sc_eliminate_fields": "0, 1",
            "condensed_field": {
                "ksp_type": "preonly",
                "pc_type": "lu",
                "pc_factor_mat_solver_type": "mumps",
            },
        }

    pressure_family = "DG"
    velocity_family = "DG"
    trace_family = "HDiv Trace"
    U = VectorFunctionSpace(mesh, velocity_family, degree)
    V = FunctionSpace(mesh, pressure_family, degree)
    T = FunctionSpace(mesh, trace_family, degree)
    W = U * V * T

    # Trial and test functions
    DPP_solution = Function(W)
    u, p, lambda_h = split(DPP_solution)
    v, q, mu_h = TestFunctions(W)

    # Mesh entities
    n = FacetNormal(mesh)
    h = CellDiameter(mesh)

    # Exact solution and source term projection
    p_e, v_e, f = decompose_exact_solution(mesh, degree)

    # Stabilizing parameter
    beta = beta_0
    if mesh_parameter:
        beta = beta / h

    # Numerical flux trace
    u_hat = u + beta * (p - lambda_h) * n

    # Flux least-squares
    a = (
        (inner(alpha() * u, v) - q * div(u) - p * div(v) + inner(grad(p), invalpha() * grad(q)))
        * delta_1
        * dx
    )
    a += delta_1 * jump(u_hat, n=n) * q("+") * dS
    a += delta_1 * dot(u_hat, n) * q * ds
    a += delta_1 * lambda_h("+") * jump(v, n=n) * dS
    a += delta_1 * lambda_h * dot(v, n) * ds

    # Mass balance least-square
    a += delta_2 * div(u) * div(v) * dx
    L = delta_2 * f * div(v) * dx

    # Irrotational least-squares
    a += delta_3 * inner(curl(alpha() * u), curl(alpha() * v)) * dx

    # Volumetric stabilizing terms
    a += stabilizing_mass_constant * (div(u) - f) * q * dx

    # Edge least-squares stabilizing term
    a += ls_lambda_constant * (lambda_h("+") - p("+")) * (mu_h("+") - q("+")) * dS

    # Hybridization terms
    a += mu_h("+") * jump(u_hat, n=n) * dS

    # Weakly imposed BC from hybridization
    # a += mu_h * (lambda_h - p_e) * ds
    a += (mu_h - q) * (lambda_h - p_e) * ds

    F = a - L

    #  Solving SC below
    PETSc.Sys.Print(
        "*******************************************\nSolving using static condensation.\n"
    )
    problem_flow = NonlinearVariationalProblem(F, DPP_solution)
    solver_flow = NonlinearVariationalSolver(problem_flow, solver_parameters=solver_parameters)
    solver_flow.solve()

    # Returning numerical and exact solutions
    p_sol, v_sol = _decompose_numerical_solution_hybrid(DPP_solution)
    return p_sol, v_sol, p_e, v_e


def dgls(
    mesh,
    degree,
    delta_0=Constant(1.0),
    delta_1=Constant(-0.5),
    delta_2=Constant(0.5),
    delta_3=Constant(0.5),
    eta_p=Constant(0.0),
    eta_u=Constant(1.0),
    mesh_parameter=True,
    solver_parameters={},
):
    if not solver_parameters:
        solver_parameters = {
            "ksp_type": "lgmres",
            "pc_type": "lu",
            "mat_type": "aij",
            "ksp_rtol": 1e-20,
            "ksp_atol": 1e-20,
            "ksp_monitor_true_residual": None,
        }

    pressure_family = "DG"
    velocity_family = "DG"
    U = VectorFunctionSpace(mesh, velocity_family, degree)
    V = FunctionSpace(mesh, pressure_family, degree)
    W = U * V

    # Trial and test functions
    DPP_solution = Function(W)
    u, p = TrialFunctions(W)
    v, q = TestFunctions(W)

    # Mesh entities
    n = FacetNormal(mesh)
    h = CellDiameter(mesh)

    # Exact solution and source term projection
    p_e, v_e, f = decompose_exact_solution(mesh, degree)

    # Average cell size and mesh dependent stabilization
    h_avg = (h("+") + h("-")) / 2.0
    if mesh_parameter:
        delta_2 = delta_2 * h * h
        delta_3 = delta_3 * h * h

    # Mixed classical terms
    a = (dot(alpha() * u, v) - div(v) * p - delta_0 * q * div(u)) * dx
    L = -delta_0 * f * q * dx - delta_0 * dot(rhob, v) * dx
    # DG terms
    a += jump(v, n) * avg(p) * dS - avg(q) * jump(u, n) * dS
    # Edge stabilizing terms
    a += (eta_u * h_avg) * avg(alpha()) * (jump(u, n) * jump(v, n)) * dS + (eta_p / h_avg) * avg(
        1.0 / alpha()
    ) * dot(jump(q, n), jump(p, n)) * dS
    # Volume stabilizing terms
    ###
    a += delta_1 * inner(invalpha() * (alpha() * u + grad(p)), delta_0 * alpha() * v + grad(q)) * dx
    ###
    a += delta_2 * alpha() * div(u) * div(v) * dx
    L += delta_2 * alpha() * f * div(v) * dx
    ###
    a += delta_3 * inner(invalpha() * curl(alpha() * u), curl(alpha() * v)) * dx
    # Weakly imposed BC
    L += (
        -dot(v, n) * p_e * ds
        - delta_1 * dot(delta_0 * alpha() * v + grad(q), invalpha() * rhob) * dx
    )

    #  Solving
    problem_flow = LinearVariationalProblem(a, L, DPP_solution, bcs=[], constant_jacobian=False)
    solver_flow = LinearVariationalSolver(
        problem_flow, options_prefix="dpp_flow", solver_parameters=solver_parameters
    )
    solver_flow.solve()

    # Returning numerical and exact solutions
    p_sol, v_sol = _decompose_numerical_solution_mixed(DPP_solution)
    return p_sol, v_sol, p_e, v_e


def dls(
    mesh,
    degree,
    eta_p=Constant(0.0),
    eta_u=Constant(1.0),
    curl_weight=Constant(1),
    mesh_parameter=True,
    solver_parameters={},
):
    if not solver_parameters:
        solver_parameters = {
            # "ksp_type": "lgmres",
            # "pc_type": "lu",
            # "mat_type": "aij",
            # "ksp_rtol": 1e-18,
            # "ksp_atol": 1e-18,
            # "ksp_monitor_true_residual": None,
            "mat_type": "aij",
            "ksp_type": "preonly",
            "pc_type": "lu",
            "pc_factor_mat_solver_type": "mumps",
            "ksp_monitor_true_residual": None,
        }

    pressure_family = "DG"
    velocity_family = "DG"
    U = VectorFunctionSpace(mesh, velocity_family, degree)
    V = FunctionSpace(mesh, pressure_family, degree)
    W = U * V

    # Trial and test functions
    DPP_solution = Function(W)
    u, p = TrialFunctions(W)
    v, q = TestFunctions(W)

    # Mesh entities
    n = FacetNormal(mesh)
    h = CellDiameter(mesh)

    # Exact solution and source term projection
    p_e, v_e, f = decompose_exact_solution(mesh, degree)

    # Boundary conditions
    # bcs = DirichletBC(W.sub(1), project(p_e, W.sub(1)), "on_boundary", method="geometric")
    # bcs = DirichletBC(W.sub(1), Constant(0.0), "on_boundary")
    bcs = DirichletBC(W.sub(0), project(v_e, W.sub(0)), "on_boundary", method="geometric")

    # Average cell size and mesh dependent stabilization
    # h_avg = (h("+") + h("-")) / 2.0
    h_avg = avg(h)

    # Stabilizing parameter
    ls_constant = Constant(1.0)
    div_stabilizing = Constant(0)  # / (Constant(1) * h * h)

    # Mixed classical terms
    # a = (
    #     (inner(alpha() * u, v) - q * div(u) - p * div(v) + inner(grad(p), invalpha() * grad(q)))
    #     * ls_constant
    #     * dx
    # )
    a = inner(alpha() * u + grad(p), v + invalpha() * grad(q)) * dx
    a += div_stabilizing * div(u) * q * dx
    a += ls_constant * div(u) * div(v) * dx
    a += curl_weight * inner(curl(alpha() * u), curl(alpha() * v)) * dx
    L = ls_constant * f * div(v) * dx
    L += div_stabilizing * f * q * dx

    # DG terms
    # These below comes from Arnold's analysis. We are using Badia & Codina stabilization approach instead.
    # a += jump(invalpha() * grad(p), n) * jump(invalpha() * grad(q), n) * dS
    # a += inner(jump(p, n), jump(q, n)) * dS
    # DG edge stabilizing terms
    # Below Badia & Codina approach is applied
    a += (eta_u * h_avg) * avg(alpha()) * (jump(u, n) * jump(v, n)) * dS
    a += (eta_p / h_avg) * avg(invalpha()) * dot(jump(q, n), jump(p, n)) * dS

    # Weakly imposed BC
    huge_number = 1e10
    nitsche_penalty = Constant(huge_number)
    a += (nitsche_penalty / h) * p * q * ds
    L += (nitsche_penalty / h) * p_e * q * ds

    #  Solving
    problem_flow = LinearVariationalProblem(a, L, DPP_solution, bcs=bcs, constant_jacobian=False)
    # problem_flow = LinearVariationalProblem(a, L, DPP_solution, bcs=[], constant_jacobian=False)
    solver_flow = LinearVariationalSolver(
        problem_flow, options_prefix="dpp_flow", solver_parameters=solver_parameters
    )
    solver_flow.solve()

    # Returning numerical and exact solutions
    p_sol, v_sol = _decompose_numerical_solution_mixed(DPP_solution)
    return p_sol, v_sol, p_e, v_e


def cgls(
    mesh,
    degree,
    delta_0=Constant(1.0),
    delta_1=Constant(-0.5),
    delta_2=Constant(0.5),
    delta_3=Constant(0.5),
    mesh_parameter=True,
    solver_parameters={},
):
    if not solver_parameters:
        solver_parameters = {
            # "ksp_type": "lgmres",
            # "pc_type": "lu",
            # "mat_type": "aij",
            # "ksp_rtol": 1e-12,
            # "ksp_atol": 1e-12,
            # "ksp_monitor_true_residual": None,
            "mat_type": "aij",
            "ksp_type": "preonly",
            "pc_type": "lu",
            "pc_factor_mat_solver_type": "mumps",
            "ksp_monitor_true_residual": None,
        }

    pressure_family = "CG"
    velocity_family = "CG"
    U = VectorFunctionSpace(mesh, velocity_family, degree)
    V = FunctionSpace(mesh, pressure_family, degree)
    W = U * V

    # Trial and test functions
    DPP_solution = Function(W)
    u, p = TrialFunctions(W)
    v, q = TestFunctions(W)

    # Mesh entities
    n = FacetNormal(mesh)
    h = CellDiameter(mesh)

    # Exact solution and source term projection
    p_e, v_e, f = decompose_exact_solution(mesh, degree)

    # Boundary conditions
    # bc_1 = DirichletBC(W.sub(0), Function(U).interpolate(v_e_1), 'on_boundary')
    # bc_2 = DirichletBC(W.sub(2), Function(U).interpolate(v_e_2), 'on_boundary')
    # bcs = [bc_1, bc_2]

    # Mesh stabilizing parameter
    if mesh_parameter:
        delta_2 = delta_2 * h * h
        delta_3 = delta_3 * h * h

    # Mixed classical terms
    a = (dot(alpha() * u, v) - div(v) * p - delta_0 * q * div(u)) * dx
    L = -delta_0 * f * q * dx - delta_0 * dot(rhob, v) * dx
    # Volume stabilizing terms
    ###
    a += delta_1 * inner(invalpha() * (alpha() * u + grad(p)), delta_0 * alpha() * v + grad(q)) * dx
    ###
    a += delta_2 * alpha() * div(u) * div(v) * dx
    L += delta_2 * alpha() * f * div(v) * dx
    ###
    a += delta_3 * inner(invalpha() * curl(alpha() * u), curl(alpha() * v)) * dx
    # Weakly imposed BC
    L += (
        -dot(v, n) * p_e * ds
        - delta_1 * dot(delta_0 * alpha() * v + grad(q), invalpha() * rhob) * dx
    )

    #  Solving
    problem_flow = LinearVariationalProblem(a, L, DPP_solution, bcs=[], constant_jacobian=False)
    solver_flow = LinearVariationalSolver(
        problem_flow, options_prefix="dpp_flow", solver_parameters=solver_parameters
    )
    solver_flow.solve()

    # Returning numerical and exact solutions
    p_sol, v_sol = _decompose_numerical_solution_mixed(DPP_solution)
    return p_sol, v_sol, p_e, v_e


def clsq(
    mesh, degree, mesh_parameter=True, solver_parameters={},
):
    if not solver_parameters:
        solver_parameters = {
            # "ksp_type": "lgmres",
            # "pc_type": "lu",
            # "ksp_rtol": 1e-18,
            # "ksp_atol": 1e-18,
            "mat_type": "aij",
            "ksp_type": "preonly",
            "pc_type": "lu",
            "pc_factor_mat_solver_type": "mumps",
            "ksp_monitor_true_residual": None,
        }

    pressure_family = "CG"
    velocity_family = "CG"
    U = VectorFunctionSpace(mesh, velocity_family, degree)
    V = FunctionSpace(mesh, pressure_family, degree)
    W = U * V

    # Trial and test functions
    DPP_solution = Function(W)
    u, p = TrialFunctions(W)
    v, q = TestFunctions(W)

    # Mesh entities
    n = FacetNormal(mesh)
    h = CellDiameter(mesh)

    # Exact solution and source term projection
    p_e, v_e, f = decompose_exact_solution(mesh, degree)

    # Strong boundary conditions
    bcs = DirichletBC(W.sub(0), project(v_e, U), "on_boundary")

    # Stabilizing parameter
    ls_constant = Constant(1.0)
    div_stabilizing = Constant(0)  # / (Constant(1) * h * h)

    # Mixed classical terms
    # a = (
    #     (inner(alpha() * u, v) - q * div(u) - p * div(v) + inner(grad(p), invalpha() * grad(q)))
    #     * ls_constant
    #     * dx
    # )
    a = inner(alpha() * u + grad(p), v + invalpha() * grad(q)) * dx
    a += div_stabilizing * div(u) * q * dx
    a += ls_constant * div(u) * div(v) * dx
    a += ls_constant * inner(curl(alpha() * u), curl(alpha() * v)) * dx
    L = ls_constant * f * div(v) * dx
    L += div_stabilizing * f * q * dx

    # Weakly imposed BC
    huge_number = 1e10
    nitsche_penalty = Constant(huge_number)
    a += (nitsche_penalty / h) * p * q * ds
    L += (nitsche_penalty / h) * p_e * q * ds

    #  Solving
    problem_flow = LinearVariationalProblem(a, L, DPP_solution, bcs=bcs, constant_jacobian=False)
    # problem_flow = LinearVariationalProblem(a, L, DPP_solution, bcs=[], constant_jacobian=False)
    solver_flow = LinearVariationalSolver(
        problem_flow, options_prefix="dpp_flow", solver_parameters=solver_parameters
    )
    solver_flow.solve()

    # Returning numerical and exact solutions
    p_sol, v_sol = _decompose_numerical_solution_mixed(DPP_solution)
    return p_sol, v_sol, p_e, v_e


def _decompose_numerical_solution_hybrid(solution):
    v_sol = solution.sub(0)
    v_sol.rename("Velocity", "label")
    p_sol = solution.sub(1)
    p_sol.rename("Pressure", "label")
    return p_sol, v_sol


def _decompose_numerical_solution_mixed(solution):
    v_sol = solution.sub(0)
    v_sol.rename("Velocity", "label")
    p_sol = solution.sub(1)
    p_sol.rename("Pressure", "label")
    return p_sol, v_sol


def decompose_exact_solution(mesh, degree, velocity_family="DG", pressure_family="DG"):
    x, y = SpatialCoordinate(mesh)
    V_e = VectorFunctionSpace(mesh, velocity_family, degree + 3)
    U_e = FunctionSpace(mesh, pressure_family, degree + 3)
    p_exact, v_exact = exact_solution.exact_solution(x, y, k, mu)
    p_e = Function(U_e).interpolate(p_exact)
    p_e.rename("Exact pressure", "label")
    v_e = Function(V_e, name="Exact velocity")
    v_e.project(-(k / mu) * grad(p_exact))
    f = Function(U_e)
    f.project(div(v_e))
    return p_e, v_e, f
