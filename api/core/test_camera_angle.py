#!/usr/bin/env python3
"""
Test camera angle detection on a local video file.

Usage:
    python test_camera_angle.py path/to/video.mp4
    python test_camera_angle.py path/to/video.mp4 --verbose
    python test_camera_angle.py path/to/video.mp4 --shots
    python test_camera_angle.py path/to/video.mp4 --shots --side left
    python test_camera_angle.py path/to/video.mp4 --frames 50

Modes:
    Default:   Run detect_camera_angle() on first N frames (quick check).
    --verbose: Frame-by-frame ratio analysis.
    --shots:   Run full LiveShotDetector pipeline. Detects actual shots and
               reports the camera angle for each one. Saves annotated debug
               frames to api/core/debug_frames/.
"""

import sys
import os
import cv2

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from live_analysis import PoseDetector, LiveShotDetector, detect_camera_angle


def print_video_info(video_path, cap):
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print(f"Video: {video_path}")
    print(f"  Resolution: {width}x{height}")
    print(f"  FPS: {fps:.1f}")
    print(f"  Total frames: {total_frames}")
    print(f"  Duration: {total_frames / fps:.1f}s")
    return total_frames, fps


def run_shots_mode(video_path, shooting_side):
    """Run the full LiveShotDetector to detect shots and report per-shot angle."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video: {video_path}")
        sys.exit(1)

    total_frames, fps = print_video_info(video_path, cap)
    print(f"  Shooting side: {shooting_side}")
    print(f"  Mode: shot detection (per-shot angle)")
    print(f"  Debug frames will be saved to: api/core/debug_frames/")
    print()

    pose = PoseDetector()
    detector = LiveShotDetector(shooting_side=shooting_side)

    shots_found = 0
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        landmarks, visibility = pose.detect(frame)
        if not landmarks:
            frame_idx += 1
            continue

        shot = detector.update(frame, landmarks, visibility)
        if shot:
            shots_found += 1
            print(f"\n  Shot {shots_found} detected at frame {frame_idx}")
            print(f"    Camera angle: {detector.camera_angle}")
            print()

        frame_idx += 1

    print(f"\nSummary:")
    print(f"  Frames processed: {frame_idx}")
    print(f"  Shots detected: {shots_found}")
    if shots_found == 0:
        print(f"  No shots detected. Try a video with a clear shooting motion.")
        print(f"  The detector looks for elbow extension > 155 deg with wrist above shoulder.")

    cap.release()
    pose.close()


def run_default_mode(video_path, num_frames, verbose):
    """Run detect_camera_angle() on first N frames."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video: {video_path}")
        sys.exit(1)

    total_frames, fps = print_video_info(video_path, cap)
    print(f"  Analyzing first {num_frames} frames...")
    print()

    pose = PoseDetector()
    angle, confidence = detect_camera_angle(pose, cap, num_frames=num_frames)

    print(f"Result:")
    print(f"  Camera angle: {angle}")
    print(f"  Confidence:   {confidence:.2f}")
    print()

    if confidence < 0.2:
        print("  Low confidence - person may not be clearly visible")
        print("  or the angle is right on the boundary between categories.")
    elif confidence > 0.7:
        print(f"  High confidence - clearly a {angle} view.")
    else:
        print(f"  Moderate confidence - likely {angle} view but could be angled.")

    if verbose:
        print()
        print("Running detailed frame-by-frame analysis...")
        print()

        pose.close()
        pose = PoseDetector()
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        import numpy as np
        ratios = []
        frames_with_pose = 0
        frames_read = 0
        for frame_idx in range(min(num_frames, total_frames)):
            ret, frame = cap.read()
            if not ret:
                break

            frames_read += 1
            landmarks, visibility = pose.detect(frame)

            if not landmarks:
                print(f"  Frame {frame_idx:3d}: no pose detected")
                continue

            frames_with_pose += 1

            left_shoulder = landmarks.get("left_shoulder")
            right_shoulder = landmarks.get("right_shoulder")
            left_hip = landmarks.get("left_hip")
            right_hip = landmarks.get("right_hip")

            ls_vis = visibility.get("left_shoulder", 0)
            rs_vis = visibility.get("right_shoulder", 0)

            if left_shoulder and right_shoulder:
                shoulder_spread = abs(left_shoulder[0] - right_shoulder[0])

                torso_height = None
                if left_hip and right_hip:
                    avg_shoulder_y = (left_shoulder[1] + right_shoulder[1]) / 2
                    avg_hip_y = (left_hip[1] + right_hip[1]) / 2
                    torso_height = abs(avg_shoulder_y - avg_hip_y)
                else:
                    for side_s, side_h in [(left_shoulder, left_hip), (right_shoulder, right_hip)]:
                        if side_s and side_h:
                            torso_height = abs(side_s[1] - side_h[1])
                            break

                if torso_height and torso_height > 0.01:
                    ratio = shoulder_spread / torso_height
                    ratios.append(ratio)

                    if ratio > 0.6:
                        label = "front"
                    elif ratio < 0.25:
                        label = "side"
                    else:
                        label = "angled"

                    print(f"  Frame {frame_idx:3d}: ratio={ratio:.3f} ({label})"
                          f"  spread={shoulder_spread:.3f}"
                          f"  torso={torso_height:.3f}"
                          f"  vis=L:{ls_vis:.2f}/R:{rs_vis:.2f}")
                else:
                    print(f"  Frame {frame_idx:3d}: pose detected but no torso height"
                          f"  vis=L:{ls_vis:.2f}/R:{rs_vis:.2f}")
            elif left_shoulder or right_shoulder:
                which = "left" if left_shoulder else "right"
                print(f"  Frame {frame_idx:3d}: only {which} shoulder visible (side view signal)"
                      f"  vis=L:{ls_vis:.2f}/R:{rs_vis:.2f}")
                ratios.append(0.0)
            else:
                print(f"  Frame {frame_idx:3d}: pose detected but no shoulders"
                      f"  landmarks: {list(landmarks.keys())[:5]}...")

        print()
        detection_rate = frames_with_pose / frames_read if frames_read > 0 else 0
        print(f"  Frames read: {frames_read}")
        print(f"  Frames with pose: {frames_with_pose} ({detection_rate:.0%} detection rate)")
        print(f"  Frames with ratio data: {len(ratios)}")
        if ratios:
            print(f"  Ratio stats: min={min(ratios):.3f}, max={max(ratios):.3f}, "
                  f"median={np.median(ratios):.3f}, mean={np.mean(ratios):.3f}")
        if detection_rate < 0.5:
            print(f"  Note: Low detection rate suggests side view or person not fully visible")

    cap.release()
    pose.close()


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h"):
        print(__doc__)
        return

    video_path = None
    verbose = False
    shots_mode = False
    shooting_side = "right"
    num_frames = 120

    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--verbose", "-v"):
            verbose = True
        elif arg == "--shots":
            shots_mode = True
        elif arg == "--side":
            if i + 1 < len(args):
                shooting_side = args[i + 1]
                i += 1
        elif arg in ("--frames", "-f"):
            if i + 1 < len(args):
                num_frames = int(args[i + 1])
                i += 1
        elif not arg.startswith("-"):
            video_path = arg
        i += 1

    if not video_path:
        print("Error: No video file specified")
        print("Usage: python test_camera_angle.py path/to/video.mp4")
        sys.exit(1)

    if not os.path.exists(video_path):
        print(f"Error: File not found: {video_path}")
        sys.exit(1)

    if shots_mode:
        run_shots_mode(video_path, shooting_side)
    else:
        run_default_mode(video_path, num_frames, verbose)


if __name__ == "__main__":
    main()
