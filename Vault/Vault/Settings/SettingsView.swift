import SwiftUI

struct SettingsView: View {
    let isOnboarding: Bool

    @Environment(AppEnvironment.self) private var env
    @State private var serverURL = ""
    @State private var username = ""
    @State private var password = ""
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
                Text("Verbinde dich mit deinem Jellyfin-Server.")
                    .font(.title3)
                    .foregroundStyle(Theme.textDim)
            }

            Form {
                Section("Jellyfin-Server") {
                    TextField("Server-URL (z. B. http://192.168.1.10:8096)", text: $serverURL)
                        .textContentType(.URL)
                }
                Section("Anmeldung") {
                    TextField("Benutzername", text: $username)
                        .textContentType(.username)
                    SecureField("Passwort", text: $password)
                        .textContentType(.password)
                    Button("Anmelden") {
                        Task { await signIn() }
                    }
                    .disabled(status == .busy)
                }
                Section("Oder: vorhandenes API-Token") {
                    TextField("Access-Token", text: $pastedToken)
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
            username = env.settings.username
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
    private func signIn() async {
        guard let url = saveServerURL() else {
            status = .failure("Bitte gültige Server-URL eingeben")
            return
        }
        status = .busy
        do {
            let auth = try await AuthService().authenticate(
                serverURL: url, username: username, password: password,
                deviceId: env.settings.deviceId
            )
            env.settings.username = username
            env.settings.token = auth.accessToken
            env.settings.userId = auth.user.id
            env.rebuildClient()
            status = .success("Angemeldet als \(auth.user.name ?? username)")
        } catch {
            status = .failure(error.localizedDescription)
        }
    }

    @MainActor
    private func validatePastedToken() async {
        guard saveServerURL() != nil else {
            status = .failure("Bitte gültige Server-URL eingeben")
            return
        }
        status = .busy
        // Temporarily store the token, validate it, and resolve the user it belongs to.
        env.settings.token = pastedToken.trimmingCharacters(in: .whitespacesAndNewlines)
        env.settings.userId = "pending"
        env.rebuildClient()
        guard let client = env.jellyfin else {
            status = .failure("Client konnte nicht erstellt werden")
            return
        }
        do {
            let user = try await AuthService().validate(client: client)
            env.settings.userId = user.id
            env.rebuildClient()
            status = .success("Token gültig — Benutzer \(user.name ?? user.id)")
        } catch {
            env.settings.clearCredentials()
            env.rebuildClient()
            status = .failure(error.localizedDescription)
        }
    }
}
