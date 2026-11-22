import SwiftUI

struct LoginView: View {

    @State private var email = ""
    @State private var password = ""
    @State private var isPasswordVisible = false
    @State private var errorMessage: String? = nil
    @State private var showDemoAlert = false

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
                                }
                                .accessibilityLabel(isPasswordVisible ? "Hide password" : "Show password")
                            }
                            .padding(16)
                            .background(Color(red: 26 / 255, green: 38 / 255, blue: 58 / 255))
                            .cornerRadius(17)
                        }
                        .padding(.top, 12)

                        if let errorMessage = errorMessage {
                            Text(errorMessage)
                                .font(.system(size: 14))
                                .foregroundColor(.red)
                        }

                        Button {
                            validateLogin()
                        } label: {
                            HStack(spacing: 10) {
                                Text("Sign In")
                                    .font(.system(size: 16, weight: .bold))
                                Image(systemName: "arrow.right")
                            }
                            .foregroundColor(.white)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 16)
                            .background(accent)
                            .cornerRadius(17)
                        }
                        .padding(.top, 24)

                        HStack(spacing: 5) {
                            Text("Don't have an account?")
                                .foregroundColor(secondaryText)

                            NavigationLink {
                                RegisterView()
                            } label: {
                                Text("Sign up")
                                    .fontWeight(.semibold)
                                    .foregroundColor(accent)
                            }
                        }
                        .font(.system(size: 14))
                        .frame(maxWidth: .infinity)
                        .padding(.top, 16)
                    }
                    .padding(.horizontal, 30)
                    .padding(.vertical, 24)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .scrollDismissesKeyboard(.interactively)
            }
            .tint(accent)
            .preferredColorScheme(.dark)
            .toolbar(.hidden, for: .navigationBar)
        }
        .alert("Demo Sign In", isPresented: $showDemoAlert) {
            Button("OK", role: .cancel) { }
        } message: {
            Text("Your inputs are valid. Firebase sign-in is not connected yet, so you have not been signed in.")
        }
    }

    // Validate locally until Firebase Authentication is connected.
    private func validateLogin() {
        errorMessage = nil

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

        showDemoAlert = true
    }
}

#Preview {
    LoginView()
}
