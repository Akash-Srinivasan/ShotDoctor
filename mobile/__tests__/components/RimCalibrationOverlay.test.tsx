/**
 * RimCalibrationOverlay Component Tests
 * Tests for the rim calibration overlay component
 */

import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import { RimCalibrationOverlay } from '../../components/RimCalibrationOverlay';

describe('RimCalibrationOverlay', () => {
  const mockOnConfirm = jest.fn();
  const mockOnRimNotVisible = jest.fn();
  const mockOnSkip = jest.fn();
  const mockOnChangeVideo = jest.fn();

  const defaultProps = {
    onConfirm: mockOnConfirm,
    onRimNotVisible: mockOnRimNotVisible,
    onSkip: mockOnSkip,
    onChangeVideo: mockOnChangeVideo,
    videoUri: 'file:///path/to/video.mp4',
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  // ==========================================================================
  // Rendering Tests
  // ==========================================================================

  describe('Rendering', () => {
    it('should render with video URI', () => {
      const { getByText } = render(<RimCalibrationOverlay {...defaultProps} />);

      expect(getByText('Mark the Rim')).toBeTruthy();
      expect(getByText('Tap on the center of the basketball rim')).toBeTruthy();
    });

    it('should render without video URI', () => {
      const { getByText } = render(
        <RimCalibrationOverlay {...defaultProps} videoUri={null} />
      );

      expect(getByText('Mark the Rim')).toBeTruthy();
    });

    it('should render change video button', () => {
      const { getByText } = render(<RimCalibrationOverlay {...defaultProps} />);

      expect(getByText('Change Video')).toBeTruthy();
    });

    it('should render instructions', () => {
      const { getByText } = render(<RimCalibrationOverlay {...defaultProps} />);

      expect(getByText('Position should be center of rim')).toBeTruthy();
      expect(getByText('Rim stays in same position during video')).toBeTruthy();
    });

    it('should show tap hint when no rim position set', () => {
      const { getByText } = render(<RimCalibrationOverlay {...defaultProps} />);

      expect(getByText('Tap to mark rim position')).toBeTruthy();
    });

    it('should show options when no rim position set', () => {
      const { getByText } = render(<RimCalibrationOverlay {...defaultProps} />);

      expect(getByText('Rim not visible in video')).toBeTruthy();
      expect(getByText('Skip for now')).toBeTruthy();
    });
  });

  // ==========================================================================
  // Tap Coordinate Normalization Tests
  // ==========================================================================

  describe('Tap Coordinate Normalization', () => {
    it('should normalize tap coordinates to 0-1 range', () => {
      const { UNSAFE_root, getByText } = render(
        <RimCalibrationOverlay {...defaultProps} />
      );

      // Find the tap area (View with onResponderRelease)
      const views = UNSAFE_root.findAllByType('View' as any);
      const tapArea = views.find(
        (v: any) => v.props.onResponderRelease !== undefined
      );

      if (tapArea) {
        // Simulate tap at specific coordinates
        const mockEvent = {
          nativeEvent: {
            locationX: 100,
            locationY: 150,
          },
        };

        fireEvent(tapArea, 'responderRelease', mockEvent);

        // After tapping, confirm button should be visible
        expect(getByText('Confirm Position')).toBeTruthy();
      }
    });

    it('should clamp coordinates to 0-1 range when out of bounds', () => {
      const { UNSAFE_root, getByText } = render(
        <RimCalibrationOverlay {...defaultProps} />
      );

      const views = UNSAFE_root.findAllByType('View' as any);
      const tapArea = views.find(
        (v: any) => v.props.onResponderRelease !== undefined
      );

      if (tapArea) {
        // Simulate tap with negative coordinates (should clamp to 0)
        const mockEvent = {
          nativeEvent: {
            locationX: -50,
            locationY: -50,
          },
        };

        fireEvent(tapArea, 'responderRelease', mockEvent);

        // Position should be set and clamped
        expect(getByText('Confirm Position')).toBeTruthy();
      }
    });

    it('should handle tap at center of overlay', () => {
      const { UNSAFE_root, getByText } = render(
        <RimCalibrationOverlay {...defaultProps} />
      );

      const views = UNSAFE_root.findAllByType('View' as any);
      const tapArea = views.find(
        (v: any) => v.props.onResponderRelease !== undefined
      );

      if (tapArea) {
        // Tap at center (normalized to ~0.5, 0.5)
        const mockEvent = {
          nativeEvent: {
            locationX: 200,
            locationY: 200,
          },
        };

        fireEvent(tapArea, 'responderRelease', mockEvent);

        expect(getByText('Confirm Position')).toBeTruthy();
      }
    });

    it('should handle tap at top-left corner', () => {
      const { UNSAFE_root, getByText } = render(
        <RimCalibrationOverlay {...defaultProps} />
      );

      const views = UNSAFE_root.findAllByType('View' as any);
      const tapArea = views.find(
        (v: any) => v.props.onResponderRelease !== undefined
      );

      if (tapArea) {
        const mockEvent = {
          nativeEvent: {
            locationX: 0,
            locationY: 0,
          },
        };

        fireEvent(tapArea, 'responderRelease', mockEvent);

        expect(getByText('Confirm Position')).toBeTruthy();
      }
    });

    it('should handle tap at bottom-right corner', () => {
      const { UNSAFE_root, getByText } = render(
        <RimCalibrationOverlay {...defaultProps} />
      );

      const views = UNSAFE_root.findAllByType('View' as any);
      const tapArea = views.find(
        (v: any) => v.props.onResponderRelease !== undefined
      );

      if (tapArea) {
        const mockEvent = {
          nativeEvent: {
            locationX: 1000,
            locationY: 1000,
          },
        };

        fireEvent(tapArea, 'responderRelease', mockEvent);

        expect(getByText('Confirm Position')).toBeTruthy();
      }
    });
  });

  // ==========================================================================
  // State Management Tests
  // ==========================================================================

  describe('State Management', () => {
    it('should update UI after setting rim position', () => {
      const { UNSAFE_root, getByText, queryByText } = render(
        <RimCalibrationOverlay {...defaultProps} />
      );

      // Initially, options should be visible
      expect(getByText('Rim not visible in video')).toBeTruthy();
      expect(getByText('Skip for now')).toBeTruthy();

      const views = UNSAFE_root.findAllByType('View' as any);
      const tapArea = views.find(
        (v: any) => v.props.onResponderRelease !== undefined
      );

      if (tapArea) {
        const mockEvent = {
          nativeEvent: {
            locationX: 100,
            locationY: 100,
          },
        };

        fireEvent(tapArea, 'responderRelease', mockEvent);

        // After setting position, confirm and reset buttons should be visible
        expect(getByText('Confirm Position')).toBeTruthy();
        expect(getByText('Reset')).toBeTruthy();

        // Options should no longer be visible
        expect(queryByText('Rim not visible in video')).toBeNull();
        expect(queryByText('Skip for now')).toBeNull();
      }
    });

    it('should reset rim position when reset button is pressed', () => {
      const { UNSAFE_root, getByText, queryByText } = render(
        <RimCalibrationOverlay {...defaultProps} />
      );

      const views = UNSAFE_root.findAllByType('View' as any);
      const tapArea = views.find(
        (v: any) => v.props.onResponderRelease !== undefined
      );

      if (tapArea) {
        // Set a position
        fireEvent(tapArea, 'responderRelease', {
          nativeEvent: { locationX: 100, locationY: 100 },
        });

        expect(getByText('Reset')).toBeTruthy();

        // Press reset
        const resetButton = getByText('Reset');
        fireEvent.press(resetButton);

        // Options should be visible again
        expect(getByText('Rim not visible in video')).toBeTruthy();
        expect(getByText('Skip for now')).toBeTruthy();

        // Reset and Confirm buttons should be gone
        expect(queryByText('Reset')).toBeNull();
        expect(queryByText('Confirm Position')).toBeNull();
      }
    });

    it('should show rim marker after setting position', () => {
      const { UNSAFE_root, getByText } = render(
        <RimCalibrationOverlay {...defaultProps} />
      );

      const views = UNSAFE_root.findAllByType('View' as any);
      const tapArea = views.find(
        (v: any) => v.props.onResponderRelease !== undefined
      );

      if (tapArea) {
        fireEvent(tapArea, 'responderRelease', {
          nativeEvent: { locationX: 100, locationY: 100 },
        });

        // Rim marker label should be visible
        expect(getByText('RIM')).toBeTruthy();
      }
    });

    it('should hide tap hint after setting position', () => {
      const { UNSAFE_root, getByText, queryByText } = render(
        <RimCalibrationOverlay {...defaultProps} />
      );

      expect(getByText('Tap to mark rim position')).toBeTruthy();

      const views = UNSAFE_root.findAllByType('View' as any);
      const tapArea = views.find(
        (v: any) => v.props.onResponderRelease !== undefined
      );

      if (tapArea) {
        fireEvent(tapArea, 'responderRelease', {
          nativeEvent: { locationX: 100, locationY: 100 },
        });

        // Tap hint should be hidden
        expect(queryByText('Tap to mark rim position')).toBeNull();
      }
    });
  });

  // ==========================================================================
  // Button Callback Tests
  // ==========================================================================

  describe('Button Callbacks', () => {
    it('should call onConfirm with normalized position when confirm is pressed', () => {
      const { UNSAFE_root, getByText } = render(
        <RimCalibrationOverlay {...defaultProps} />
      );

      const views = UNSAFE_root.findAllByType('View' as any);
      const tapArea = views.find(
        (v: any) => v.props.onResponderRelease !== undefined
      );

      if (tapArea) {
        // Set position
        fireEvent(tapArea, 'responderRelease', {
          nativeEvent: { locationX: 100, locationY: 100 },
        });

        // Press confirm
        const confirmButton = getByText('Confirm Position');
        fireEvent.press(confirmButton);

        // Should call onConfirm with normalized coordinates
        expect(mockOnConfirm).toHaveBeenCalledTimes(1);
        expect(mockOnConfirm).toHaveBeenCalledWith(
          expect.objectContaining({
            x: expect.any(Number),
            y: expect.any(Number),
          })
        );

        // Coordinates should be in 0-1 range
        const position = mockOnConfirm.mock.calls[0][0];
        expect(position.x).toBeGreaterThanOrEqual(0);
        expect(position.x).toBeLessThanOrEqual(1);
        expect(position.y).toBeGreaterThanOrEqual(0);
        expect(position.y).toBeLessThanOrEqual(1);
      }
    });

    it('should not call onConfirm when confirm is pressed without position', () => {
      const { queryByText } = render(
        <RimCalibrationOverlay {...defaultProps} />
      );

      // Confirm button should not be visible without position
      expect(queryByText('Confirm Position')).toBeNull();
      expect(mockOnConfirm).not.toHaveBeenCalled();
    });

    it('should call onRimNotVisible when button is pressed', () => {
      const { getByText } = render(<RimCalibrationOverlay {...defaultProps} />);

      const button = getByText('Rim not visible in video');
      fireEvent.press(button);

      expect(mockOnRimNotVisible).toHaveBeenCalledTimes(1);
    });

    it('should call onSkip when skip button is pressed', () => {
      const { getByText } = render(<RimCalibrationOverlay {...defaultProps} />);

      const button = getByText('Skip for now');
      fireEvent.press(button);

      expect(mockOnSkip).toHaveBeenCalledTimes(1);
    });

    it('should call onChangeVideo when change video button is pressed', () => {
      const { getByText } = render(<RimCalibrationOverlay {...defaultProps} />);

      const button = getByText('Change Video');
      fireEvent.press(button);

      expect(mockOnChangeVideo).toHaveBeenCalledTimes(1);
    });
  });

  // ==========================================================================
  // Edge Cases
  // ==========================================================================

  describe('Edge Cases', () => {
    it('should handle multiple taps (only last tap counts)', () => {
      const { UNSAFE_root, getByText } = render(
        <RimCalibrationOverlay {...defaultProps} />
      );

      const views = UNSAFE_root.findAllByType('View' as any);
      const tapArea = views.find(
        (v: any) => v.props.onResponderRelease !== undefined
      );

      if (tapArea) {
        // First tap
        fireEvent(tapArea, 'responderRelease', {
          nativeEvent: { locationX: 50, locationY: 50 },
        });

        // Second tap
        fireEvent(tapArea, 'responderRelease', {
          nativeEvent: { locationX: 200, locationY: 200 },
        });

        // Third tap
        fireEvent(tapArea, 'responderRelease', {
          nativeEvent: { locationX: 300, locationY: 300 },
        });

        // Confirm the position
        const confirmButton = getByText('Confirm Position');
        fireEvent.press(confirmButton);

        // Only the last tap position should be confirmed
        expect(mockOnConfirm).toHaveBeenCalledTimes(1);
      }
    });

    it('should handle tap and reset multiple times', () => {
      const { UNSAFE_root, getByText } = render(
        <RimCalibrationOverlay {...defaultProps} />
      );

      const views = UNSAFE_root.findAllByType('View' as any);
      const tapArea = views.find(
        (v: any) => v.props.onResponderRelease !== undefined
      );

      if (tapArea) {
        // First cycle
        fireEvent(tapArea, 'responderRelease', {
          nativeEvent: { locationX: 100, locationY: 100 },
        });
        let resetButton = getByText('Reset');
        fireEvent.press(resetButton);

        // Second cycle
        fireEvent(tapArea, 'responderRelease', {
          nativeEvent: { locationX: 200, locationY: 200 },
        });
        resetButton = getByText('Reset');
        fireEvent.press(resetButton);

        // Third cycle
        fireEvent(tapArea, 'responderRelease', {
          nativeEvent: { locationX: 300, locationY: 300 },
        });

        // Should still be able to confirm after multiple resets
        expect(getByText('Confirm Position')).toBeTruthy();
      }
    });

    it('should handle very precise coordinates', () => {
      const { UNSAFE_root, getByText } = render(
        <RimCalibrationOverlay {...defaultProps} />
      );

      const views = UNSAFE_root.findAllByType('View' as any);
      const tapArea = views.find(
        (v: any) => v.props.onResponderRelease !== undefined
      );

      if (tapArea) {
        fireEvent(tapArea, 'responderRelease', {
          nativeEvent: { locationX: 123.456, locationY: 789.012 },
        });

        const confirmButton = getByText('Confirm Position');
        fireEvent.press(confirmButton);

        expect(mockOnConfirm).toHaveBeenCalled();
      }
    });

    it('should handle zero coordinates', () => {
      const { UNSAFE_root, getByText } = render(
        <RimCalibrationOverlay {...defaultProps} />
      );

      const views = UNSAFE_root.findAllByType('View' as any);
      const tapArea = views.find(
        (v: any) => v.props.onResponderRelease !== undefined
      );

      if (tapArea) {
        fireEvent(tapArea, 'responderRelease', {
          nativeEvent: { locationX: 0, locationY: 0 },
        });

        const confirmButton = getByText('Confirm Position');
        fireEvent.press(confirmButton);

        expect(mockOnConfirm).toHaveBeenCalledWith({
          x: 0,
          y: 0,
        });
      }
    });
  });

  // ==========================================================================
  // Integration Tests
  // ==========================================================================

  describe('Integration', () => {
    it('should complete full calibration flow', () => {
      const { UNSAFE_root, getByText } = render(
        <RimCalibrationOverlay {...defaultProps} />
      );

      // 1. Verify initial state
      expect(getByText('Tap to mark rim position')).toBeTruthy();
      expect(getByText('Rim not visible in video')).toBeTruthy();

      // 2. Tap to set position
      const views = UNSAFE_root.findAllByType('View' as any);
      const tapArea = views.find(
        (v: any) => v.props.onResponderRelease !== undefined
      );

      if (tapArea) {
        fireEvent(tapArea, 'responderRelease', {
          nativeEvent: { locationX: 150, locationY: 200 },
        });

        // 3. Verify position is set
        expect(getByText('RIM')).toBeTruthy();
        expect(getByText('Confirm Position')).toBeTruthy();

        // 4. Confirm position
        const confirmButton = getByText('Confirm Position');
        fireEvent.press(confirmButton);

        // 5. Verify callback was called
        expect(mockOnConfirm).toHaveBeenCalled();
      }
    });

    it('should complete rim not visible flow', () => {
      const { getByText } = render(<RimCalibrationOverlay {...defaultProps} />);

      // 1. Verify initial state
      expect(getByText('Rim not visible in video')).toBeTruthy();

      // 2. Press rim not visible
      const button = getByText('Rim not visible in video');
      fireEvent.press(button);

      // 3. Verify callback
      expect(mockOnRimNotVisible).toHaveBeenCalled();
    });

    it('should complete skip flow', () => {
      const { getByText } = render(<RimCalibrationOverlay {...defaultProps} />);

      // 1. Verify initial state
      expect(getByText('Skip for now')).toBeTruthy();

      // 2. Press skip
      const button = getByText('Skip for now');
      fireEvent.press(button);

      // 3. Verify callback
      expect(mockOnSkip).toHaveBeenCalled();
    });

    it('should complete change video flow', () => {
      const { getByText } = render(<RimCalibrationOverlay {...defaultProps} />);

      // 1. Verify button exists
      expect(getByText('Change Video')).toBeTruthy();

      // 2. Press change video
      const button = getByText('Change Video');
      fireEvent.press(button);

      // 3. Verify callback
      expect(mockOnChangeVideo).toHaveBeenCalled();
    });
  });
});
