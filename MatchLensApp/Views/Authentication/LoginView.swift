
import SwiftUI

struct LoginView: View {

    @State private var email = ""
    @State private var password = ""
    @State private var isPasswordVisible = false
    @State private var errorMessage: String? = nil
    @State private var showDemoAlert = false

    var body: some View {
        // The sign-up link needs a navigation container to open RegisterView.
        NavigationStack {
            loginForm
        }
        .alert("Demo Sign In", isPresented: $showDemoAlert) {
            Button("OK", role: .cancel) { }
        } message: {
            Text("Your inputs are valid. Firebase sign-in is not connected yet, so you have not been signed in.")
        }
    }

    private var loginForm: some View {
        ZStack {

            // MatchLens dark navy background
            Color(red: 0.04, green: 0.06, blue: 0.12)
                .ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: 12) {

                    // Circular MatchLens logo
                    VStack(spacing: 8) {
                        Text("ML")
                            .font(.system(size: 56, weight: .bold))
                            .foregroundColor(
                                Color(red: 0.65, green: 1.0, blue: 0.0)
                            )
                            .frame(width: 200, height: 200)
                            .background(
                                Color(red: 0.13, green: 0.20, blue: 0.32)
                            )
                            .clipShape(Circle())

                        Text("MatchLens")
                            .font(.system(size: 20, weight: .semibold))
                            .foregroundColor(.white)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.bottom, 30)

                    // Welcome message
                    Text("Welcome back")
                        .font(.system(size: 32, weight: .bold))
                        .foregroundColor(.white)

                    Text("Log in to your football moments")
                        .font(.system(size: 16))
                        .foregroundColor(.gray)

                    // Email input field
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Email address")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(.white)

                        TextField("Enter your email address", text: $email)
                            .keyboardType(.emailAddress)
                            .textContentType(.username)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .foregroundColor(.white)
                            .padding(16)
                            .background(
                                Color(red: 0.10, green: 0.16, blue: 0.25)
                            )
                            .cornerRadius(12)
                    }
                    .padding(.top, 24)

                    // Password input field
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
                            .textContentType(.password)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .foregroundColor(.white)

                            Button {
                                isPasswordVisible.toggle()
                            } label: {
                                Image(systemName: isPasswordVisible ? "eye.slash" : "eye")
                                    .foregroundColor(.gray)
                            }
                            .accessibilityLabel(
                                isPasswordVisible ? "Hide password" : "Show password"
                            )
                        }
                        .padding(16)
                        .background(
                            Color(red: 0.10, green: 0.16, blue: 0.25)
                        )
                        .cornerRadius(12)
                    }
                    .padding(.top, 12)

                    if let errorMessage = errorMessage {
                        Text(errorMessage)
                            .font(.system(size: 14))
                            .foregroundColor(.red)
                            .accessibilityLabel("Sign-in error: \(errorMessage)")
                    }

                    // Sign In button
                    Button {
                        validateLogin()
                    } label: {
                        HStack(spacing: 10) {
                            Text("Sign In")
                                .font(.system(size: 16, weight: .semibold))

                            Image(systemName: "arrow.right")
                        }
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 16)
                        .background(
                            Color(red: 0.18, green: 0.48, blue: 1.0)
                        )
                        .cornerRadius(12)
                    }
                    .padding(.top, 24)

                    // Registration link
                    HStack(spacing: 5) {
                        Text("Don't have an account?")
                            .foregroundColor(.gray)
                        NavigationLink {
                            RegisterView()
                        } label: {
                            Text("Sign up")
                                .fontWeight(.semibold)
                                .foregroundColor(
                                    Color(red: 0.18, green: 0.48, blue: 1.0)
                                )
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

        let emailPattern = #"^[A-Z0-9a-z._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"#
        guard trimmedEmail.range(of: emailPattern, options: .regularExpression) != nil else {
            errorMessage = "Please enter a valid email address."
            return
        }

        // Do not trim passwords or apply new-account rules to existing accounts.
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
