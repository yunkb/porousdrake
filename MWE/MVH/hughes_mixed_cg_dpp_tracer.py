"""
The present code is based in the code and method proposed in [1], but adapted from [2]. Here I just use as a reference
code, since the mentioned paper is a benchmark for my own work.

Ref:
[1] S.H.S. Joodat, K.B. Nakshatrala, R. Ballarini, Modeling flow in porous media with double porosity/permeability:
A stabilized mixed formulation, error analysis, and numerical solutions, Computer Methods in Applied Mechanics and
Engineering, Volume 337, 2018, Pages 632-676, ISSN 0045-7825, https://doi.org/10.1016/j.cma.2018.04.004.
[2] Joshaghani, M. S., S. H. S. Joodat, and K. B. Nakshatrala. "A stabilized mixed discontinuous Galerkin formulation
for double porosity/permeability model." arXiv preprint arXiv:1805.01389 (2018).
"""
from firedrake import *
import numpy as np
import random

try:
    import matplotlib.pyplot as plt
except:
    warning("Matplotlib not imported")

random.seed(222)
nx, ny = 50, 20
Lx, Ly = 1.0, 0.4
quadrilateral = False
mesh = RectangleMesh(nx, ny, Lx, Ly, quadrilateral=quadrilateral)

degree = 1
velSpace = VectorFunctionSpace(mesh, "CG", degree + 1)
pSpace = FunctionSpace(mesh, "CG", degree)
wSpace = MixedFunctionSpace([velSpace, pSpace, velSpace, pSpace])

uSpace = FunctionSpace(mesh, "CG", 1)
kSpace = FunctionSpace(mesh, "DG", 0)

mu0, Rc, D = Constant(1e-3), Constant(3.0), Constant(2e-6)
tol = 1e-14

k1_0 = 1.1
k1_1 = 0.9


class myk1(Expression):
    def eval(self, values, x):
        if x[1] < Ly / 2.0 + tol:
            values[0] = k1_0
        else:
            values[0] = k1_1


k1 = interpolate(myk1(), kSpace)

k2_0 = 0.01 * k1_0
k2_1 = 0.01 * k1_1


class myk2(Expression):
    def eval(self, values, x):
        if x[1] < Ly / 2.0 + tol:
            values[0] = k2_0
        else:
            values[0] = k2_1


k2 = interpolate(myk2(), kSpace)


def alpha1(c):
    return mu0 * exp(Rc * (1.0 - c)) / k1


def invalpha1(c):
    return 1.0 / alpha1(c)


def alpha2(c):
    return mu0 * exp(Rc * (1.0 - c)) / k2


def invalpha2(c):
    return 1.0 / alpha2(c)


v_topbottom = Constant(0.0)
p_L = Constant(10.0)
p_R = Constant(1.0)
c_inj = Constant(1.0)


class c_0(Expression):
    def eval(self, values, x):
        if x[0] < 0.010 * Lx:
            values[0] = abs(0.1 * exp(-x[0] * x[0]) * random.random())
        else:
            values[0] = 0.0


(v1, p1, v2, p2) = TrialFunctions(wSpace)
(w1, q1, w2, q2) = TestFunctions(wSpace)
DPP_solution = Function(wSpace)

c1 = TrialFunction(uSpace)
u = TestFunction(uSpace)
conc = Function(uSpace)
conc_k = interpolate(c_0(), uSpace)

T = 1.5e-3
dt = 5e-5

bcDPP = []
bcleft_c = DirichletBC(uSpace, c_inj, 1)
bcAD = [bcleft_c]

rhob1, rhob2 = Constant((0.0, 0.0)), Constant((0.0, 0.0))
f = Constant(0.0)

n = FacetNormal(mesh)
h = CellDiameter(mesh)

aDPP = (
    dot(w1, alpha1(conc_k) * v1) * dx
    + dot(w2, alpha2(conc_k) * v2) * dx
    - div(w1) * p1 * dx
    - div(w2) * p2 * dx
    + q1 * div(v1) * dx
    + q2 * div(v2) * dx
    + q1 * (invalpha1(conc_k) / k1) * (p1 - p2) * dx
    - q2 * (invalpha2(conc_k) / k2) * (p1 - p2) * dx
    - 0.5
    * dot(alpha1(conc_k) * w1 - grad(q1), invalpha1(conc_k) * (alpha1(conc_k) * v1 + grad(p1)))
    * dx
    - 0.5
    * dot(alpha2(conc_k) * w2 - grad(q2), invalpha2(conc_k) * (alpha2(conc_k) * v2 + grad(p2)))
    * dx
)
aDPP += (
    dot(w1, n) * p1 * ds(3)
    + dot(w2, n) * p2 * ds(3)
    - q1 * dot(v1, n) * ds(3)
    - q2 * dot(v2, n) * ds(3)
    + dot(w1, n) * p1 * ds(4)
    + dot(w2, n) * p2 * ds(4)
    - q1 * dot(v1, n) * ds(4)
    - q2 * dot(v2, n) * ds(4)
)
LDPP = (
    dot(w1, rhob1) * dx
    + dot(w2, rhob2) * dx
    - dot(w1, n) * p_L * ds(1)
    - dot(w2, n) * p_L * ds(1)
    - dot(w1, n) * p_R * ds(2)
    - dot(w2, n) * p_R * ds(2)
    - 0.5 * dot(alpha1(conc_k) * w1 - grad(q1), invalpha1(conc_k) * rhob1) * dx
    - 0.5 * dot(alpha2(conc_k) * w2 - grad(q2), invalpha2(conc_k) * rhob2) * dx
)

vnorm = sqrt(
    dot((DPP_solution.sub(0) + DPP_solution.sub(2)), (DPP_solution.sub(0) + DPP_solution.sub(2)))
)

taw = h / (2.0 * vnorm) * dot((DPP_solution.sub(0) + DPP_solution.sub(2)), grad(u))

a_r = (
    taw
    * (c1 + dt * (dot((DPP_solution.sub(0) + DPP_solution.sub(2)), grad(c1)) - div(D * grad(c1))))
    * dx
)

L_r = taw * (conc_k + dt * f) * dx

aAD = (
    a_r
    + u * c1 * dx
    + dt
    * (
        u * dot((DPP_solution.sub(0) + DPP_solution.sub(2)), grad(c1)) * dx
        + dot(grad(u), D * grad(c1)) * dx
    )
)

LAD = L_r + u * conc_k * dx + dt * u * f * dx

cfile = File("Concentration.pvd")
v1file = File("Macro_Velocity.pvd")
p1file = File("Macro_Pressure.pvd")
v2file = File("Micro_Velocity.pvd")
p2file = File("Micro_Pressure.pvd")

solver_parameters = {
    "ksp_type": "lgmres",
    "pc_type": "lu",
    "mat_type": "aij",
    "ksp_rtol": 1e-5,
    "ksp_monitor_true_residual": True,
}

problem_flow = LinearVariationalProblem(
    aDPP, LDPP, DPP_solution, bcs=bcDPP, constant_jacobian=False
)
solver_flow = LinearVariationalSolver(
    problem_flow, options_prefix="flow_", solver_parameters=solver_parameters
)

t = dt
while t <= T:
    print("============================")
    print("\ttime =", t)
    print("============================")
    c_0.t = t

    solver_flow.solve()

    solve(aAD == LAD, conc, bcs=bcAD)
    conc_k.assign(conc)

    cfile.write(conc, time=t)
    v1file.write(DPP_solution.sub(0), time=t)
    p1file.write(DPP_solution.sub(1), time=t)
    v2file.write(DPP_solution.sub(2), time=t)
    p2file.write(DPP_solution.sub(3), time=t)

    t += dt

print("total time = ", t)
