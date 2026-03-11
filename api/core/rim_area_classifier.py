#!/usr/bin/env python3
"""
Rim Area Classifier for Basketball Make/Miss Detection

Binary classifier that determines if a basketball passed through the hoop
by analyzing rim-area crops from outcome frames.

Uses YOLOv8n-cls model trained on rim-area crops labeled as:
- "ball_through_hoop": Ball passing through or just passed through rim
- "ball_not_through_hoop": Ball near rim but not going through

The classifier:
1. Takes 128x128 crops centered on the rim area
2. Runs inference on each crop
3. Returns confidence scores for each class
4. Aggregates multiple frames to vote on final make/miss outcome

Usage:
    from rim_area_classifier import RimAreaClassifier

    classifier = RimAreaClassifier()

    # Single frame
    made, confidence = classifier.classify_crop(crop_img)

    # Multi-frame sequence (recommended)
    result = classifier.classify_sequence([crop1, crop2, crop3, ...])
    # result = {"made": True, "confidence": 0.85, "through_count": 3, ...}
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


class RimAreaClassifier:
    """
    Binary classifier for basketball make/miss detection from rim-area crops.

    Attributes:
        model: YOLOv8n-cls model instance (None if not loaded)
        device: Inference device ("mps", "cuda", or "cpu")
        enabled: True if model loaded successfully
        confidence_threshold: Minimum confidence for high-confidence predictions
    """

    def __init__(self, model_path: Optional[str] = None):
        """
        Initialize the rim area classifier.

        Args:
            model_path: Path to YOLOv8n-cls model file. If None, looks for
                       "rim_classifier_model.pt" in the same directory as this file.

        Note:
            If the model file is not found or cannot be loaded, the classifier
            will be disabled (self.enabled = False) and all methods will return
            safe defaults.
        """
        self.model = None
        self.device = "cpu"
        self.enabled = False
        self.confidence_threshold = 0.6

        # Class name mapping (from YOLOv8-cls training)
        self.class_names = {
            0: "ball_through_hoop",
            1: "ball_not_through_hoop"
        }

        try:
            from ultralytics import YOLO
            import torch

            # Resolve model path
            if model_path is None:
                model_path = str(Path(__file__).parent / "rim_classifier_model.pt")

            if not Path(model_path).exists():
                print(f"⚠️  Rim classifier model not found at {model_path}")
                print("   Classifier disabled — shot outcomes will use trajectory + Gemini only")
                self.enabled = False
                return

            print(f"Loading rim classifier model: {model_path}")
            self.model = YOLO(model_path)

            # Device selection (same priority as CustomBallTracker)
            if torch.backends.mps.is_available():
                self.device = "mps"
                print("  Using Apple Silicon GPU (MPS)")
            elif torch.cuda.is_available():
                self.device = "cuda"
                print("  Using NVIDIA GPU (CUDA)")
            else:
                self.device = "cpu"
                print("  Using CPU")

            self.enabled = True
            print("✓ Rim classifier loaded")

        except ImportError:
            print("⚠️  ultralytics not installed. Run: pip install ultralytics")
            print("   Rim classifier disabled")
            self.enabled = False
        except Exception as e:
            print(f"⚠️  Could not load rim classifier: {e}")
            self.enabled = False

    def warm_up(self) -> None:
        """
        Warm up GPU with a dummy inference to avoid slow first request.

        Should be called once at startup after model initialization.
        """
        if not self.enabled or self.model is None:
            return

        try:
            # Create a dummy 128x128 RGB image
            dummy = np.zeros((128, 128, 3), dtype=np.uint8)
            self.model(dummy, verbose=False, device=self.device, imgsz=128)
            print("  GPU warmup complete")
        except Exception as e:
            print(f"⚠️  Warmup failed: {e}")

    def classify_crop(self, crop: np.ndarray) -> Tuple[Optional[bool], float]:
        """
        Classify a single rim-area crop.

        Args:
            crop: RGB image crop (any size, will be resized to 128x128)

        Returns:
            (made, confidence) where:
                made: True if ball through hoop, False if not, None if uncertain
                confidence: Model confidence score [0.0, 1.0]

        Note:
            Returns (None, 0.0) if classifier is disabled.
        """
        if not self.enabled or self.model is None:
            return (None, 0.0)

        try:
            # Resize to model input size
            if crop.shape[:2] != (128, 128):
                crop_resized = cv2.resize(crop, (128, 128))
            else:
                crop_resized = crop

            # Run inference
            results = self.model(
                crop_resized,
                verbose=False,
                device=self.device,
                imgsz=128
            )

            # Parse classification results
            # YOLOv8-cls returns probabilities for each class
            if len(results) == 0 or not hasattr(results[0], 'probs'):
                return (None, 0.0)

            probs = results[0].probs

            # Get class with highest probability
            top_class = int(probs.top1)  # Index of highest probability class
            top_conf = float(probs.top1conf)  # Confidence of highest class

            # Map class index to make/miss
            class_name = self.class_names.get(top_class, "unknown")

            if class_name == "ball_through_hoop":
                return (True, top_conf)
            elif class_name == "ball_not_through_hoop":
                return (False, top_conf)
            else:
                return (None, top_conf)

        except Exception as e:
            print(f"⚠️  Rim classifier inference error: {e}")
            return (None, 0.0)

    def classify_sequence(self, crops: List[np.ndarray]) -> Dict:
        """
        Classify a sequence of rim-area crops and vote on the outcome.

        This is the recommended method for shot outcome classification as it
        aggregates evidence across multiple frames to reduce false positives.

        Args:
            crops: List of RGB image crops from outcome window frames

        Returns:
            Dictionary with:
                made: True if >= 2 frames show through with conf > threshold
                      False if 0 frames show through
                      None if unclear (1 frame or low confidence)
                confidence: Average confidence across all frames
                through_count: Number of frames classified as "through hoop"
                total_frames: Total frames analyzed
                high_conf_count: Frames with confidence > threshold

        Algorithm:
            - If >= 2 frames show "through" with conf > 0.6 → made = True
            - If 0 frames show "through" → made = False
            - Otherwise → made = None (unclear)

        Note:
            Returns safe defaults if classifier is disabled.
        """
        if not self.enabled or self.model is None:
            return {
                "made": None,
                "confidence": 0.0,
                "through_count": 0,
                "total_frames": len(crops),
                "high_conf_count": 0
            }

        if not crops:
            return {
                "made": None,
                "confidence": 0.0,
                "through_count": 0,
                "total_frames": 0,
                "high_conf_count": 0
            }

        # Classify each crop
        classifications = []
        confidences = []

        for crop in crops:
            made, conf = self.classify_crop(crop)
            classifications.append(made)
            confidences.append(conf)

        # Count outcomes
        through_count = sum(1 for c in classifications if c is True)
        high_conf_through = sum(
            1 for made, conf in zip(classifications, confidences)
            if made is True and conf > self.confidence_threshold
        )
        high_conf_count = sum(1 for conf in confidences if conf > self.confidence_threshold)

        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        # Voting logic
        # Need at least 2 high-confidence "through" frames to call it a make
        if high_conf_through >= 2:
            final_made = True
        # If no frames show "through", it's a miss
        elif through_count == 0:
            final_made = False
        # Otherwise unclear (1 frame, low confidence, etc.)
        else:
            final_made = None

        return {
            "made": final_made,
            "confidence": round(avg_confidence, 3),
            "through_count": through_count,
            "total_frames": len(crops),
            "high_conf_count": high_conf_count,
            "high_conf_through": high_conf_through
        }


def main():
    """
    Simple test script for the rim area classifier.

    Usage:
        python rim_area_classifier.py <image_path>
        python rim_area_classifier.py <dir_of_crops>
    """
    if len(sys.argv) < 2:
        print("Usage: python rim_area_classifier.py <image_path_or_dir>")
        sys.exit(1)

    path = Path(sys.argv[1])
    classifier = RimAreaClassifier()

    if not classifier.enabled:
        print("Classifier not loaded. Exiting.")
        sys.exit(1)

    # Warm up
    classifier.warm_up()

    if path.is_file():
        # Single image
        img = cv2.imread(str(path))
        if img is None:
            print(f"Could not load image: {path}")
            sys.exit(1)

        made, conf = classifier.classify_crop(img)
        print(f"\nSingle frame result:")
        print(f"  Made: {made}")
        print(f"  Confidence: {conf:.3f}")

    elif path.is_dir():
        # Directory of crops
        image_files = sorted(path.glob("*.jpg")) + sorted(path.glob("*.png"))
        if not image_files:
            print(f"No .jpg or .png files found in {path}")
            sys.exit(1)

        crops = []
        for img_path in image_files:
            img = cv2.imread(str(img_path))
            if img is not None:
                crops.append(img)

        result = classifier.classify_sequence(crops)
        print(f"\nSequence result ({len(crops)} frames):")
        print(f"  Made: {result['made']}")
        print(f"  Confidence: {result['confidence']:.3f}")
        print(f"  Through count: {result['through_count']}/{result['total_frames']}")
        print(f"  High conf frames: {result['high_conf_count']}")
        print(f"  High conf through: {result['high_conf_through']}")

    else:
        print(f"Path not found: {path}")
        sys.exit(1)


if __name__ == "__main__":
    main()
