import SwiftUI

/// Cold-start intro: an amber safe dial spins, unlocks with a warm flash, then
/// two vault doors slide apart to reveal the app. Plays once per launch and is
/// fully deterministic, so it can never block startup.
struct VaultIntroView: View {
    var onFinished: () -> Void

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @AppStorage("introSoundEnabled") private var soundEnabled = true

    @State private var sound: IntroSound?
    @State private var rotation: Double = 0
    @State private var dialOpacity: Double = 0
    @State private var dialScale: CGFloat = 0.86
    @State private var glow: Double = 0
    @State private var doorGap: CGFloat = 0
    @State private var didFinish = false

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let h = geo.size.height
            ZStack {
                door(mirrored: false)
                    .frame(width: w / 2, height: h)
                    .position(x: w / 4 - doorGap * (w / 2), y: h / 2)
                door(mirrored: true)
                    .frame(width: w / 2, height: h)
                    .position(x: w * 3 / 4 + doorGap * (w / 2), y: h / 2)

                ZStack {
                    Circle()
                        .fill(RadialGradient(
                            colors: [Theme.accent.opacity(0.18 + glow * 0.35), .clear],
                            center: .center, startRadius: 0, endRadius: 340
                        ))
                        .frame(width: 680, height: 680)
                    SafeDial(rotation: rotation)
                        .frame(width: 360, height: 360)
                }
                .scaleEffect(dialScale)
                .opacity(dialOpacity)
                .brightness(glow * 0.25)
            }
            .frame(width: w, height: h)
        }
        .ignoresSafeArea()
        .task { await run() }
    }

    @ViewBuilder
    private func door(mirrored: Bool) -> some View {
        ZStack(alignment: mirrored ? .leading : .trailing) {
            Theme.bg
            LinearGradient(colors: [.white.opacity(0.025), .clear], startPoint: .top, endPoint: .bottom)
            Rectangle().fill(Theme.accent.opacity(0.35)).frame(width: 1.5)
        }
    }

    private func run() async {
        if reduceMotion {
            withAnimation(.easeOut(duration: 0.3)) { dialOpacity = 1; dialScale = 1 }
            try? await Task.sleep(for: .seconds(0.6))
            withAnimation(.easeIn(duration: 0.3)) { dialOpacity = 0 }
            try? await Task.sleep(for: .seconds(0.3))
            finish()
            return
        }
        if soundEnabled { sound = IntroSound() }
        withAnimation(.easeOut(duration: 0.45)) { dialOpacity = 1; dialScale = 1 }
        withAnimation(.easeInOut(duration: 1.25)) { rotation = 720 }
        sound?.play("dial_spin", volume: 0.45)
        try? await Task.sleep(for: .seconds(1.3))
        sound?.play("unlock_clunk", volume: 0.85)
        withAnimation(.easeOut(duration: 0.22)) { glow = 1 }
        try? await Task.sleep(for: .seconds(0.3))
        withAnimation(.easeIn(duration: 0.3)) { glow = 0; dialOpacity = 0 }
        try? await Task.sleep(for: .seconds(0.22))
        sound?.play("door_open", volume: 0.7)
        withAnimation(.easeIn(duration: 0.6)) { doorGap = 1 }
        try? await Task.sleep(for: .seconds(0.62))
        finish()
    }

    private func finish() {
        guard !didFinish else { return }
        didFinish = true
        onFinished()
    }
}

/// The combination dial: a ring with graduation ticks and a centre hub that
/// rotate, plus a fixed index pointer at the top. Matches the app icon.
private struct SafeDial: View {
    var rotation: Double

    var body: some View {
        GeometryReader { geo in
            let s = min(geo.size.width, geo.size.height)
            let r = s * 0.34
            ZStack {
                ZStack {
                    Circle()
                        .stroke(Theme.accent, lineWidth: s * 0.02)
                        .frame(width: r * 2, height: r * 2)
                    ForEach(0..<12, id: \.self) { i in
                        if i != 0 {
                            Capsule()
                                .fill(Theme.accent)
                                .frame(width: s * 0.011, height: s * 0.05)
                                .offset(y: -r * 1.12)
                                .rotationEffect(.degrees(Double(i) * 30))
                        }
                    }
                    Circle().fill(Theme.accent).frame(width: s * 0.085, height: s * 0.085)
                }
                .rotationEffect(.degrees(rotation))

                DialPointer()
                    .fill(Theme.accent)
                    .frame(width: s * 0.06, height: s * 0.05)
                    .offset(y: -r * 1.2)
            }
            .frame(width: geo.size.width, height: geo.size.height)
        }
    }
}

/// Downward-pointing triangle used as the dial's fixed index marker.
private struct DialPointer: Shape {
    func path(in rect: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: rect.midX, y: rect.maxY))
        p.addLine(to: CGPoint(x: rect.minX, y: rect.minY))
        p.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
        p.closeSubpath()
        return p
    }
}
