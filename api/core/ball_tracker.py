from ultralytics import YOLO
import supervision as sv
import numpy as np
import pandas as pd
import sys
sys.path.append("../")  # Adjust the path to import from the parent directory
from utils import read_stub, save_stub  # Import stub utilities

# we can ignore the tracking for the ball and just use the detection


class BallTracker:
    def __init__(self, model_path):
        self.model = YOLO(model_path)
    
    def detect_frames(self, frames):
        batch_size=20
        detections=[]
        for i in range(0, len(frames), batch_size):
            batch_frames=frames[i:i+batch_size]
            batch_detections=self.model.predict(batch_frames, conf=0.5)
            detections+=batch_detections
        return detections
    
    def get_object_tracks(self, frames, read_from_stub=False, stub_path=None):
        
        tracks = read_stub(read_from_stub, stub_path) 
        if tracks is not None:
            if len(tracks) == len(frames):
                return tracks
            

        detections = self.detect_frames(frames)
        tracks = []

        for frame_num, detection in enumerate(detections):
            cls_names = detection.names
            cls_names_inv = {v:k for k,v in cls_names.items()}

            detection_supervision = sv.Detections.from_ultralytics(detection)   
            tracks.append({})
            chosen_bbox = None
            max_confidence = 0
            
            for frame_detection in detection_supervision:
                bbox = frame_detection[0].tolist()
                cls_id = frame_detection[3]
                confidence = frame_detection[2]

                if cls_id == cls_names_inv["Ball"]:
                    if max_confidence < confidence:
                        chosen_bbox = bbox
                        max_confidence = confidence

            if chosen_bbox is not None:
                tracks[frame_num][1] = {"bbox": chosen_bbox}

        
        save_stub(stub_path, tracks)  # Save the tracks to a stub file
        # the whole stub thing was to provide checkpoints in the code so that if it crashes, we can resume from the last checkpoint
        # this is useful for long videos where the tracker takes a lot of time to run   
        return tracks



# Ball interpolation 
# fucntion that will sipress detections based nt he distance form the previous detection

    def remove_wrong_detections(self,ball_positions):
        """
        Filter out incorrect ball detections based on maximum allowed movement distance.

        Args:
            ball_positions (list): List of detected ball positions across frames.

        Returns:
            list: Filtered ball positions with incorrect detections removed.
        """
        
        maximum_allowed_distance = 25
        last_good_frame_index = -1

        for i in range(len(ball_positions)):
            current_box = ball_positions[i].get(1, {}).get('bbox', [])

            if len(current_box) == 0:
                continue

            if last_good_frame_index == -1:
                # First valid detection
                last_good_frame_index = i
                continue

            last_good_box = ball_positions[last_good_frame_index].get(1, {}).get('bbox', [])
            frame_gap = i - last_good_frame_index
            adjusted_max_distance = maximum_allowed_distance * frame_gap

            if np.linalg.norm(np.array(last_good_box[:2]) - np.array(current_box[:2])) > adjusted_max_distance:
                ball_positions[i] = {}
            else:
                last_good_frame_index = i

        return ball_positions
    

    def interpolate_ball_positions(self, ball_positions):
        ball_positions = [x.get(1,{}).get('bbox', []) for x in ball_positions]
        df_ball_positions = pd.DataFrame(ball_positions, columns=["x1", "y1", "x2", "y2"])

        #Interpolate missing values
        df_ball_positions = df_ball_positions.interpolate()
        df_ball_positions = df_ball_positions.bfill()

        ball_positions = [{1:{"bbox":x}} for x in df_ball_positions.to_numpy().tolist()]
    
        return ball_positions

import cv2
import numpy as np
import warnings
import supervision as sv
from rfdetr import RFDETRBase
from rfdetr.util.coco_classes import COCO_CLASSES
import cvzone

# suppress the upcoming torch.meshgrid warning
warnings.filterwarnings(
    "ignore",
    message="torch.meshgrid: in an upcoming release, it will be required to pass the indexing argument"
)

# --- Config ---
WEIGHTS_PATH = "checkpoint_best_regular.pth"
VIDEO_SOURCE = "Videos/warmupshots.mp4"
DISPLAY_W, DISPLAY_H = 800, 600
CAPTURE_W, CAPTURE_H = 1280, 720
CONF_THRESH = 0.3
TARGET_CLASS = 1  # the class_id you want to track 37 for coco base model
MIN_PTS_FIT = 5

# --- Init RF-DETR ---
model = RFDETRBase(pretrain_weights=WEIGHTS_PATH) #pretrain_weights=WEIGHTS_PATH
print(f"Loaded RF-DETR weights from {WEIGHTS_PATH}")

# --- Init ByteTrack ---
tracker = sv.ByteTrack()

# --- Buffers for trajectory ---
xs, ys = [], []
coeffs = None
paused = False

# --- Video capture & window setup ---
cap = cv2.VideoCapture(VIDEO_SOURCE)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_W)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_H)

cv2.namedWindow("Trajectory Prediction", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Trajectory Prediction", DISPLAY_W, DISPLAY_H)

box_annotator = sv.BoxAnnotator()
label_annotator = sv.LabelAnnotator()

print("Press SPACE to pause/resume, 'q' to quit.")

while True:
    if not paused:
        ret, frame = cap.read()
        if not ret:
            break

        # 1) Detect
        det = model.predict(frame[:, :, ::-1].copy(), threshold=CONF_THRESH)

        # 2) Filter class_id == TARGET_CLASS
        mask = (det.class_id == TARGET_CLASS)
        bboxes = det.xyxy[mask]
        confs = det.confidence[mask]

        if len(bboxes):
            # 3) Convert to Supervision Detections
            detections = sv.Detections(
                xyxy=bboxes,
                confidence=confs,
                class_id=det.class_id[mask]
            )

            # 4) Track with ByteTrack
            detections = tracker.update_with_detections(detections)

            if len(detections.xyxy) == 0:
                cv2.putText(frame, "Tracking lost", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            else:
                # use first detected track
                x1, y1, x2, y2 = detections.xyxy[0]
                track_id = detections.tracker_id[0]

                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)

                # draw tracking box & label
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (255, 0, 255), 2)
                cv2.circle(frame, (cx, cy), 4, (0, 255, 0), -1)
                cv2.putText(frame, f"ID:{int(track_id)}", (int(x1), int(y1) - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)

                # 5) Bounce detection
                if ys and cy < ys[-1] - 2:
                    xs.clear()
                    ys.clear()
                    coeffs = None
                    print("Bounce → resetting trajectory fit")

                xs.append(cx)
                ys.append(cy)

                # draw past points
                for px, py in zip(xs, ys):
                    cv2.circle(frame, (px, py), 3, (0, 200, 0), -1)

                # 6) Fit parabola & draw prediction
                if len(xs) >= MIN_PTS_FIT:
                    coeffs = np.polyfit(xs, ys, 2)
                    a, b, c = coeffs
                    for t in range(0, CAPTURE_W, 5):
                        y_pred = int(a * t * t + b * t + c)
                        cv2.circle(frame, (t, y_pred), 2, (255, 0, 255), 3)

        # Show frame
        cvzone.putTextRect(frame,
                           "SPACE = Pause/Resume   |   Q = Quit",
                           (10, frame.shape[0] - 20),
                           # colorB=(255, 255, 255),
                           colorR=(0, 0, 0),
                           scale=3,
                           thickness=3
                           )
        cv2.imshow("Trajectory Prediction", frame)

    # Handle keypress
    key = cv2.waitKey(30) & 0xFF
    if key == ord('q'):
        break
    elif key == 32:  # SPACE
        paused = not paused
        print("Paused" if paused else "Resumed")

cap.release()
cv2.destroyAllWindows()
