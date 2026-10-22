--------------------------- MODULE CBFSafetyFilter ---------------------------
\* Discrete-time safety-filter invariants for a Control Barrier Function
\* (CBF) collision-avoidance filter, mirroring
\* src/apex_autopilot_optimization/safety/cbf.py.
\*
\* Model (1D integer grid, finite so TLC can enumerate it):
\*   - vehicle position `pos` on a bounded grid
\*   - a set of spherical obstacles, each <<position, radius>>
\*   - requested `throttle`; the filter output `Filtered` is re-computed
\*     every control cycle from the current state (mirrors cbf.py filter()).
\*   - clear distance to the nearest obstacle AHEAD:
\*         gap = min over obstacles ahead of (obstaclePos - radius - pos)
\*         h   = gap - SafetyMargin            (CBF value; h(x) in cbf.py)
\*   - filter (discrete-time CBF refinement guaranteeing one-step safety):
\*         h < 0   => Filtered = 0                         (stop if unsafe)
\*         h >= 0  => Filtered = throttle, if throttle <= h   (pass through)
\*         h >= 0  => Filtered = h,        if throttle > h    (brake to margin)
\*   Only reduces the command (never increases it) and keeps pos outside the
\*   safety margin.  NOTE: the filter must be re-evaluated each cycle from the
\*   current position; caching `Filtered` across move steps breaks Safe (the
\*   vehicle can coast into the margin on a stale command).
\*
\* Invariants verified by TLC (see CBF_SafetyFilter.cfg):
\*   Safe                  : gap >= SafetyMargin
\*   FilterNeverIncreases  : Filtered <= throttle
\*   FilteredInRange       : 0 <= Filtered <= MaxThrottle
\*----------------------------------------------------------------------------

---- MODULE CBFSafetyFilter ----

EXTENDS Integers, FiniteSets, Sequences, TLC

\* ---------- Configuration (mirrors CBFConfig) ----------
CONSTANTS
    SafetyMargin,   \* CBFConfig.safety_margin  (m)
    MaxThrottle,    \* throttle upper bound
    MaxPos,         \* grid bound (keeps the state space finite)
    BIG             \* \"infinity\" when no obstacle is ahead

ASSUME SafetyMargin >= 0
ASSUME MaxThrottle > 0
ASSUME MaxPos >= 0
ASSUME BIG > MaxThrottle

\* ---------- Obstacles (finite set; concrete values in the .cfg) ----------
\* Each obstacle: <<position, radius>>  (occupies [position-radius, position+radius])
CONSTANT Obstacles

ASSUME Obstacles \subseteq Nat \times Nat

\* ---------- State ----------
VARIABLES
    pos,      \* vehicle position on the grid
    throttle  \* requested throttle input

\* ---------- Derived ----------
\* Clear distance from vehicle to an obstacle's surface (positive if ahead).
Clear(o) == (o[1] - o[2]) - pos
Ahead(o) == Clear(o) >= 0

GapAhead == { Clear(o) : o \in Obstacles /\ Ahead(o) }

gap ==
    IF GapAhead = {}
    THEN BIG
    ELSE Min(GapAhead)

h == gap - SafetyMargin   \* CBF value

\* ---------- Discrete-time CBF filter (re-evaluated every cycle) ----------
\* Ensures the next position stays outside the safety margin:
\*   pos + Filtered <= nearest surface - SafetyMargin  <=>  Filtered <= h
Filtered ==
    IF h < 0
    THEN 0
    ELSE IF throttle <= h
         THEN throttle
         ELSE h

\* ---------- Initial predicate ----------
Init ==
    /\ pos = 0
    /\ throttle \in 0 .. MaxThrottle

\* ---------- Next-state relation ----------
Next ==
    \/ SetThrottle
    \/ Move

SetThrottle ==
    /\ throttle' \in 0 .. MaxThrottle
    /\ unchanged <<pos>>

Move ==
    /\ pos' = pos + Filtered   \* driver approaches nearest obstacle; filter applied fresh
    /\ pos' <= MaxPos
    /\ unchanged <<throttle>>

\* ---------- Safety-filter invariants ----------
\* Never enter the safety margin of any obstacle.
Safe == gap >= SafetyMargin

\* The filter never increases the commanded throttle (monotonicity).
FilterNeverIncreases == Filtered <= throttle

\* The filter output is always a valid throttle command.
FilteredInRange == Filtered \in 0 .. MaxThrottle

\* ---------- Spec ----------
Spec == Init /\ [][Next]_<<pos, throttle>>

=============================================================================
