import SwiftUI
import UIKit

/// A transparent full-screen UIViewRepresentable that reads continuous swipe
/// gestures from the Siri Remote touch surface via `UIPanGestureRecognizer`
/// configured for indirect touches.
///
/// Usage in the player ZStack:
/// ```swift
/// SiriRemoteScrubGesture(
///     onBegin: { model.beginScrub() },
///     onChange: { fraction in model.updateScrub(fraction: fraction) },
///     onEnd:   { model.commitScrub() },
///     onCancel: { model.cancelScrub() }
/// )
/// ```
/// `onChange` receives the cumulative horizontal translation expressed as a
/// fraction of the view's width (positive = forward, negative = backward).
struct SiriRemoteScrubGesture: UIViewRepresentable {

    /// Called once when the finger first touches the remote surface.
    var onBegin: () -> Void
    /// Called on every update with `translation.x / view.bounds.width`.
    var onChange: (Double) -> Void
    /// Called when the gesture ends normally — commit the scrub.
    var onEnd: () -> Void
    /// Called when the gesture is cancelled or fails — cancel the scrub.
    var onCancel: () -> Void

    // MARK: - UIViewRepresentable

    func makeCoordinator() -> Coordinator {
        Coordinator(onBegin: onBegin, onChange: onChange, onEnd: onEnd, onCancel: onCancel)
    }

    func makeUIView(context: Context) -> UIView {
        let view = UIView()
        view.backgroundColor = .clear
        view.isUserInteractionEnabled = true

        let pan = UIPanGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.handlePan(_:)))
        // On tvOS the Siri Remote touch surface sends indirect touches.
        pan.allowedTouchTypes = [NSNumber(value: UITouch.TouchType.indirect.rawValue)]
        view.addGestureRecognizer(pan)
        context.coordinator.gestureRecognizer = pan

        return view
    }

    func updateUIView(_ uiView: UIView, context: Context) {
        // Refresh closures so they always capture the latest SwiftUI state.
        context.coordinator.onBegin  = onBegin
        context.coordinator.onChange = onChange
        context.coordinator.onEnd    = onEnd
        context.coordinator.onCancel = onCancel
    }

    // MARK: - Coordinator

    final class Coordinator: NSObject {
        var onBegin:  () -> Void
        var onChange: (Double) -> Void
        var onEnd:    () -> Void
        var onCancel: () -> Void

        /// Retain the recognizer so we can read its view geometry.
        weak var gestureRecognizer: UIPanGestureRecognizer?

        init(onBegin: @escaping () -> Void,
             onChange: @escaping (Double) -> Void,
             onEnd: @escaping () -> Void,
             onCancel: @escaping () -> Void) {
            self.onBegin  = onBegin
            self.onChange = onChange
            self.onEnd    = onEnd
            self.onCancel = onCancel
        }

        @objc func handlePan(_ recognizer: UIPanGestureRecognizer) {
            guard let view = recognizer.view else { return }
            let width = max(view.bounds.width, 1)

            switch recognizer.state {
            case .began:
                onBegin()

            case .changed:
                let tx = recognizer.translation(in: view).x
                onChange(Double(tx / width))

            case .ended:
                onEnd()

            case .cancelled, .failed:
                onCancel()

            default:
                break
            }
        }
    }
}
