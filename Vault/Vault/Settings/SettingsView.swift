import SwiftUI

struct SettingsView: View {
    let isOnboarding: Bool

    @Environment(AppEnvironment.self) private var env
    @State private var serverURL = ""
    @State private var pastedToken = ""
    @State private var status: Status = .idle

    enum Status: Equatable {
        case idle, busy
        case success(String)
        case failure(String)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 30) {
            if isOnboarding {
                Text("◆ VAULT")
                    .font(.system(size: 46, weight: .heavy))
                    .kerning(10)
                    .foregroundStyle(Theme.accent)
            }

            Form {
                Section("vault-api") {
                    TextField("API-URL (z. B. http://192.168.1.10:8787)", text: $serverURL)
                        .textContentType(.URL)
                    TextField("Bearer-Token aus /admin", text: $pastedToken)
                    Button("Token prüfen & speichern") {
                        Task { await validatePastedToken() }
                    }
                    .disabled(status == .busy)
                }
                Section {
                    statusRow
                    if env.isConfigured {
                        Button("Abmelden", role: .destructive) {
                            env.signOut()
                            status = .idle
                        }
                    }
                }
            }
        }
        .padding(isOnboarding ? Theme.screenPadding : 0)
        .background(Theme.bg)
        .navigationTitle(isOnboarding ? "" : "Einstellungen")
        .onAppear {
            serverURL = env.settings.serverURLString
            pastedToken = env.settings.token ?? ""
        }
    }

    @ViewBuilder
    private var statusRow: some View {
        switch status {
        case .idle:
            EmptyView()
        case .busy:
            HStack(spacing: 16) {
                ProgressView()
                Text("Verbinde …").foregroundStyle(Theme.textDim)
            }
        case .success(let message):
            Label(message, systemImage: "checkmark.circle.fill")
                .foregroundStyle(.green)
        case .failure(let message):
            Label(message, systemImage: "exclamationmark.triangle.fill")
                .foregroundStyle(.red)
        }
    }

    private func saveServerURL() -> URL? {
        env.settings.serverURLString = serverURL
        return env.settings.serverURL
    }

    @MainActor
    private func validatePastedToken() async {
        guard saveServerURL() != nil else {
            status = .failure("Bitte gültige API-URL eingeben")
            return
        }
        let token = pastedToken.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !token.isEmpty else {
            status = .failure("Bitte Bearer-Token eingeben")
            return
        }
        status = .busy
        env.settings.token = token
        env.rebuildClient()
        guard let client = env.vault else {
            status = .failure("Client konnte nicht erstellt werden")
            return
        }
        do {
            try await client.validateBearer()
            status = .success("vault-api verbunden")
        } catch {
            env.settings.clearCredentials()
            env.rebuildClient()
            status = .failure(error.localizedDescription)
        }
    }
}
