# Gesture-Based Volume Controller

A real-time hand gesture volume controller built using OpenCV, MediaPipe, and Pycaw.

## Features

* Real-time hand tracking
* Gesture-based volume control
* Volume smoothing for stable adjustments
* Pinch-and-hold mute gesture
* Volume lock mechanism
* Hand-movement-based unlock system
* Real-time FPS monitoring
* Visual volume feedback

## How It Works

The application detects hand landmarks using MediaPipe Hands and tracks the distance between the thumb tip and index finger tip.

* Increasing the distance raises the volume
* Decreasing the distance lowers the volume
* Holding a pinch gesture toggles mute
* Keeping the hand stable locks the current volume
* Moving the hand unlocks the volume

## Tech Stack

* Python
* OpenCV
* MediaPipe
* Pycaw
* NumPy

## Future Improvements

* Brightness control
* Media playback controls
* Multi-gesture support
* Cross-platform audio control
