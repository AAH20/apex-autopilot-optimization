# Aggregated upstream telemetry for ONE vehicle (AAS sim -> apex).
# Topic: /Drone{id}/telemetry/vehicle_telemetry  and  /fleet/telemetry/aggregate
# One message per vehicle per publish cycle; fields are latest-snapshot values.

std_msgs/Header header          # stamp = ROS2/sim time; frame_id = "base_link"/"odom"
uint8  drone_id                 # DRONE_ID == ROS_DOMAIN_ID == MAV_SYS_ID (AAS convention)

# ---- Pose (from /fmu/out/vehicle_odometry, /fmu/out/vehicle_local_position) ----
float64 x                       # m, position (frame per pose_frame, default NED)
float64 y
float64 z
float64 roll                    # rad
float64 pitch
float64 yaw
uint8  pose_frame               # VehicleOdometry.pose_frame: 1=NED earth-fixed, 2=FRD world-fixed

# ---- Velocity (from /fmu/out/vehicle_odometry) ----
float64 vx                      # m/s
float64 vy
float64 vz
uint8  velocity_frame           # VehicleOdometry.velocity_frame

# ---- Battery (from /fmu/out/battery_status) ----
float32 battery_voltage         # V
float32 battery_current         # A (negative = discharging)
float32 battery_remaining       # 0..1 fraction remaining
uint8  battery_charge_state     # BatteryStatus.BATTERY_CHARGING_STATE_* enum

# ---- GPS / global position (from /fmu/out/vehicle_gps_position, /fmu/out/vehicle_global_position) ----
float64 lat                     # deg WGS84
float64 lon                     # deg WGS84
float32 alt_amsl                # m AMSL
float32 alt_ellipsoid           # m
uint8  gps_fix_type             # GPS fix type (0=no GPS … 5=RTK fixed)
uint8  nsat                     # number of satellites
float32 eph                     # m horizontal error
float32 epv                     # m vertical error
float32 ground_speed            # m/s

# ---- Mode & armed status (from /fmu/out/vehicle_status) ----
uint8  nav_state                # PX4 navigation state (OFFBOARD=14, AUTO_MISSION=15, HOLD=4, …)
uint8  arming_state             # 1=DISARMED, 2=ARMED
uint8  vehicle_type             # 1=ROTARY_WING, 2=FIXED_WING, 3=ROVER
bool   pre_flight_checks_pass
bool   is_vtol
bool   in_transition_mode

# ---- Provenance ----
uint64 timestamp_us             # PX4 timestamp (micros) of the source update
string source                   # originating AAS node (e.g. "px4_interface", "yolo_node")
