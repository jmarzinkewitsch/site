import AVFoundation
import SwiftUI
import UIKit

/// Hosts the AVSampleBufferDisplayLayer the engine renders into.
struct VideoLayerView: UIViewRepresentable {
    let onLayer: (AVSampleBufferDisplayLayer) -> Void

    func makeUIView(context: Context) -> DisplayView {
        let view = DisplayView()
        onLayer(view.displayLayer)
        return view
    }

    func updateUIView(_ uiView: DisplayView, context: Context) {}

    final class DisplayView: UIView {
        override class var layerClass: AnyClass { AVSampleBufferDisplayLayer.self }

        /// `layerClass` guarantees the backing layer's type, so the cast always
        /// succeeds; the guard keeps a future change to that invariant from
        /// becoming a hard crash and surfaces it in debug instead.
        var displayLayer: AVSampleBufferDisplayLayer {
            guard let layer = layer as? AVSampleBufferDisplayLayer else {
                assertionFailure("DisplayView.layer must be AVSampleBufferDisplayLayer")
                return AVSampleBufferDisplayLayer()
            }
            return layer
        }

        override init(frame: CGRect) {
            super.init(frame: frame)
            backgroundColor = .black
            displayLayer.videoGravity = .resizeAspect
        }

        @available(*, unavailable)
        required init?(coder: NSCoder) { fatalError() }
    }
}
