# Single YOLO detection (AAS yolo_node -> apex). Wire-compatible with vision_msgs/Detection2D fields.
std_msgs/Header header
uint8  drone_id
string class_id                 # class label (from COCO names file)
float64 score                   # 0..1 confidence
# Bounding box, normalized image coordinates (0..1)
float64 center_x
float64 center_y
float64 size_x
float64 size_y
# YOLO26 3D direction estimate (px4_offboard reads pose.pose.position.x/y as az/el deg)
float64 azimuth_deg             # deg
float64 elevation_deg           # deg
float64 depth_m                 # m, NaN when depth unavailable
