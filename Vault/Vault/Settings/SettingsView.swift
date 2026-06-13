import SwiftUI

struct SettingsView: View {
    let isOnboarding: Bool

    @Environment(AppEnvironment.self) private var env
    @State private var serverURL = ""
    @State private var pastedToken = ""
    @State private var status: Status = .idle

    enum Status: Equatable { case idle, busy, success(String), failure(String) }

    var body: some View {
        VStack(alignment: .leading, spacing: 30) {
            if isOnboarding {
                Text("◆ VAULT")
                    .font(.system(size: 46, weight: .heavy))
                    .kerning(10)
                    .foregroundStyle(Theme.accent)
                Text("Verbinde dich mit deiner vault-api.")
                    .font(.title3)
                    .foregroundStyle(Theme.textDim)
            }

            Form {
                Section("vault-api") {
                    TextField("API-URL (z. B. http://192.168.1.10:8088)", text: $serverURL)
                        .textContentType(.URL)
                    SecureField("Vault-Bearer-Token", text: $pastedToken)
                    Button("Speichern & prüfen") { Task { await validateVaultAPI() } }
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

    @ViewBuilder private var statusRow: some View {
        switch status {
        case .idle: EmptyView()
        case .busy:
            HStack(spacing: 16) { ProgressView(); Text("Prüfe vault-api …").foregroundStyle(Theme.textDim) }
        case .success(let message): Label(message, systemImage: "checkmark.circle.fill").foregroundStyle(.green)
        case .failure(let message): Label(message, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.red)
        }
    }

    private func save() -> Bool {
        env.settings.serverURLString = serverURL.trimmingCharacters(in: .whitespacesAndNewlines)
        env.settings.token = pastedToken.trimmingCharacters(in: .whitespacesAndNewlines)
        env.settings.userId = "vault"
        env.settings.username = "vault-api"
        env.rebuildClient()
        return env.isConfigured
    }

    @MainActor private func validateVaultAPI() async {
        guard save(), let client = env.vault else {
            status = .failure("Bitte API-URL und Bearer-Token eingeben")
            return
        }
        status = .busy
        do {
            let _: HealthResponse = try await client.get("health")
            status = .success("vault-api gespeichert")
        } catch {
            status = .failure(error.localizedDescription)
        }
    }
}

private struct HealthResponse: Decodable { let status: String }
