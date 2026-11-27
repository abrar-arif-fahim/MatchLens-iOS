import SwiftUI

struct LoginView: View {
    @EnvironmentObject private var app: AppStore

    @State private var email = ""
    @State private var password = ""
    @State private var isPasswordVisible = false
    @State private var errorMessage: String? = nil

    private let secondaryText = Color(red: 166 / 255, green: 185 / 255, blue: 209 / 255)
    private let accent = Color(red: 41 / 255, green: 119 / 255, blue: 250 / 255)

    var body: some View {
        NavigationStack {
            ZStack {
                Color(red: 11 / 255, green: 15 / 255, blue: 31 / 255)
                    .ignoresSafeArea()

                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        VStack(spacing: 8) {
                            Text("ML")
                                .font(.system(size: 56, weight: .bold))
                                .foregroundColor(Color(red: 240 / 255, green: 243 / 255, blue: 251 / 255))
                                .frame(width: 200, height: 200)
                                .background(Color(red: 0.13, green: 0.20, blue: 0.32))
                                .clipShape(Circle())

                            Text("MatchLens")
                                .font(.system(size: 20, weight: .semibold))
                                .foregroundColor(.white)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.bottom, 30)

                        Text("Welcome back")
                            .font(.system(size: 30, weight: .bold))
                            .foregroundColor(Color(red: 240 / 255, green: 243 / 255, blue: 251 / 255))

                        Text("Log in to your football moments")
                            .font(.system(size: 14))
                            .foregroundColor(secondaryText)

                        VStack(alignment: .leading, spacing: 8) {
                            Text("Email address")
                                .font(.system(size: 14, weight: .medium))
                                .foregroundColor(.white)

                            TextField("Enter your email address", text: $email)
                                .font(.system(size: 14))
                                .keyboardType(.emailAddress)
                                .textContentType(.username)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()
                                .foregroundColor(.white)
                                .padding(16)
                                .background(Color(red: 26 / 255, green: 38 / 255, blue: 58 / 255))
                                .cornerRadius(17)
                        }
                        .padding(.top, 24)

                        VStack(alignment: .leading, spacing: 8) {
                            Text("Password")
                                .font(.system(size: 14, weight: .medium))
                                .foregroundColor(.white)

                            HStack(spacing: 12) {
                                Group {
                                    if isPasswordVisible {
                                        TextField("Enter your password", text: $password)
                                    } else {
                                        SecureField("Enter your password", text: $password)
                                    }
                                }
                                .font(.system(size: 14))
                                .textContentType(.password)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()
                                .foregroundColor(.white)

                                Button {
                                    isPasswordVisible.toggle()
                                } label: {
                                    Image(systemName: isPasswordVisible ? "eye.slash" : "eye")
                                        .foregroundColor(secondaryText)
                                        .frame(width: 44, height: 44).contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                                .accessibilityLabel(isPasswordVisible ? "Hide password" : "Show password")
                            }
                            .padding(16)
                            .background(Color(red: 26 / 255, green: 38 / 255, blue: 58 / 255))
                            .cornerRadius(17)
                        }
                        .padding(.top, 12)

                        if let errorMessage = errorMessage {
                            Text(errorMessage)
                                .font(.subheadline)
                                .foregroundColor(.red)
                                .accessibilityLabel("Sign-in error: \(errorMessage)")
                        }
                        if let error = app.errorMessage {
                            Text(error).font(.subheadline).foregroundStyle(.red)
                                .accessibilityLabel("Sign-in error: \(error)")
                        }

                        Button {
                            validateLogin()
                        } label: {
                            HStack(spacing: 10) {
                                if app.authBusy { ProgressView().tint(.white).accessibilityHidden(true) }
                                Text(app.authBusy ? "Signing in…" : "Sign In").font(.headline)
                                if !app.authBusy { Image(systemName: "arrow.right").accessibilityHidden(true) }
                            }
                            .foregroundColor(.white)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 16)
                            .background(accent)
                            .cornerRadius(17)
                        }
                        .disabled(app.authBusy)
                        .padding(.top, 24)

                        AdaptiveActionRow {
                            Text("Don't have an account?")
                                .foregroundColor(secondaryText)

                            NavigationLink {
                                RegisterView()
                            } label: {
                                Text("Sign up")
                                    .fontWeight(.semibold)
                                    .foregroundColor(accent)
                                    .frame(minHeight: 44)
                            }
                            .disabled(app.authBusy)
                        }
                        .font(.subheadline)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 16)
                    }
                    .padding(.horizontal, 30)
                    .padding(.vertical, 24)
                    .frame(maxWidth: 500)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .scrollDismissesKeyboard(.interactively)
                .disabled(app.authBusy)
            }
            .tint(accent)
            .preferredColorScheme(.dark)
            .toolbar(.hidden, for: .navigationBar)
        }
        .onAppear { app.errorMessage = nil }
    }

    // Firebase alone decides whether locally validated credentials are accepted.
    private func validateLogin() {
        guard !app.authBusy else { return }
        errorMessage = nil
        app.errorMessage = nil

        let trimmedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedEmail.isEmpty else {
            errorMessage = "Please enter your email address."
            return
        }

        guard AuthenticationValidation.isValidEmail(trimmedEmail) else {
            errorMessage = "Please enter a valid email address."
            return
        }

        guard !password.isEmpty else {
            errorMessage = "Please enter your password."
            return
        }

        let submittedPassword = password
        Task {
            await app.signIn(email: trimmedEmail, password: submittedPassword)
            password = ""
        }
    }
}

#Preview {
    LoginView().environmentObject(AppStore())
}
