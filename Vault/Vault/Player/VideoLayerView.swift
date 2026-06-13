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

        var displayLayer: AVSampleBufferDisplayLayer {
            layer as! AVSampleBufferDisplayLayer
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
