
import SwiftUI

struct RegisterView: View {

    // MARK: - Input States
    @State private var fullName = ""
    @State private var email = ""
    @State private var password = ""
    @State private var confirmPassword = ""

    // MARK: - UI States
    @State private var isPasswordVisible = false
    @State private var isConfirmPasswordVisible = false
    @State private var isLoading = false
    @State private var errorMessage: String? = nil
    @State private var showSuccessAlert = false

    // Navigation back to Login
    @Environment(\.dismiss) private var dismiss

    // MARK: - Body
    var body: some View {

        ZStack {

            // MatchLens dark navy background
            Color(red: 0.04, green: 0.06, blue: 0.12)
                .ignoresSafeArea()

            ScrollView {

                VStack(alignment: .leading, spacing: 16) {

                    // MARK: - Logo
                    VStack(spacing: 10) {

                        Text("ML")
                            .font(.system(size: 36, weight: .bold))
                            .foregroundColor(
                                Color(red: 0.65, green: 1.0, blue: 0.0)
                            )
                            .frame(width: 100, height: 100)
                            .background(
                                Color(red: 0.13, green: 0.20, blue: 0.32)
                            )
                            .clipShape(Circle())

                        Text("MatchLens")
                            .font(.system(size: 20, weight: .semibold))
                            .foregroundColor(.white)

                        Text("Create Account")
                            .font(.system(size: 30, weight: .bold))
                            .foregroundColor(.white)

                        Text("Join MatchLens and explore football moments")
                            .font(.system(size: 14))
                            .foregroundColor(.gray)
                            .multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.bottom, 20)

                    // MARK: - Full Name
                    VStack(alignment: .leading, spacing: 8) {

                        Text("Full Name")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(.white)

                        TextField("Enter your full name", text: $fullName)
                            .textContentType(.name)
                            .textInputAutocapitalization(.words)
                            .foregroundColor(.white)
                            .padding(16)
                            .background(
                                Color(red: 0.10, green: 0.16, blue: 0.25)
                            )
                            .cornerRadius(12)
                    }

                    // MARK: - Email
                    VStack(alignment: .leading, spacing: 8) {

                        Text("Email Address")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(.white)

                        TextField("Enter your email address", text: $email)
                            .keyboardType(.emailAddress)
                            .textContentType(.emailAddress)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .foregroundColor(.white)
                            .padding(16)
                            .background(
                                Color(red: 0.10, green: 0.16, blue: 0.25)
                            )
                            .cornerRadius(12)
                    }

                    // MARK: - Password
                    VStack(alignment: .leading, spacing: 8) {

                        Text("Password")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(.white)

                        HStack(spacing: 12) {

                            Group {
                                if isPasswordVisible {
                                    TextField(
                                        "Create a password",
                                        text: $password
                                    )
                                } else {
                                    SecureField(
                                        "Create a password",
                                        text: $password
                                    )
                                }
                            }
                            .textContentType(.newPassword)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .foregroundColor(.white)

                            Button {
                                isPasswordVisible.toggle()
                            } label: {
                                Image(
                                    systemName: isPasswordVisible
                                    ? "eye.slash" : "eye"
                                )
                                .foregroundColor(.gray)
                            }
                            .accessibilityLabel(
                                isPasswordVisible
                                ? "Hide password" : "Show password"
                            )
                        }
                        .padding(16)
                        .background(
                            Color(red: 0.10, green: 0.16, blue: 0.25)
                        )
                        .cornerRadius(12)

                        Text("Minimum 8 characters, including uppercase, lowercase and a number.")
                            .font(.system(size: 12))
                            .foregroundColor(.gray)
                    }

                    // MARK: - Confirm Password
                    VStack(alignment: .leading, spacing: 8) {

                        Text("Confirm Password")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(.white)

                        HStack(spacing: 12) {

                            Group {
                                if isConfirmPasswordVisible {
                                    TextField(
                                        "Confirm your password",
                                        text: $confirmPassword
                                    )
                                } else {
                                    SecureField(
                                        "Confirm your password",
                                        text: $confirmPassword
                                    )
                                }
                            }
                            .textContentType(.newPassword)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .foregroundColor(.white)

                            Button {
                                isConfirmPasswordVisible.toggle()
                            } label: {
                                Image(
                                    systemName: isConfirmPasswordVisible
                                    ? "eye.slash" : "eye"
                                )
                                .foregroundColor(.gray)
                            }
                            .accessibilityLabel(
                                isConfirmPasswordVisible
                                ? "Hide password" : "Show password"
                            )
                        }
                        .padding(16)
                        .background(
                            Color(red: 0.10, green: 0.16, blue: 0.25)
                        )
                        .cornerRadius(12)
                    }

                    // MARK: - Validation Error
                    if let errorMessage = errorMessage {

                        Text(errorMessage)
                            .font(.system(size: 14))
                            .foregroundColor(.red)
                    }

                    // MARK: - Sign Up Button (local validation only)
                    Button {
                        registerAccount()
                    } label: {

                        HStack(spacing: 10) {

                            if isLoading {
                                ProgressView()
                                    .tint(.white)
                            } else {
                                Text("Sign Up")
                                    .font(
                                        .system(
                                            size: 16,
                                            weight: .semibold
                                        )
                                    )

                                Image(systemName: "arrow.right")
                            }
                        }
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 16)
                        .background(
                            Color(red: 0.18, green: 0.48, blue: 1.0)
                        )
                        .cornerRadius(12)
                    }
                    .disabled(isLoading)
                    .padding(.top, 12)

                    // MARK: - Sign In Link
                    HStack(spacing: 5) {

                        Text("Already have an account?")
                            .foregroundColor(.gray)

                        Button {
                            dismiss()
                        } label: {
                            Text("Sign In")
                                .fontWeight(.semibold)
                                .foregroundColor(
                                    Color(
                                        red: 0.18,
                                        green: 0.48,
                                        blue: 1.0
                                    )
                                )
                        }
                    }
                    .font(.system(size: 14))
                    .frame(maxWidth: .infinity)
                    .padding(.top, 12)

                }
                .padding(.horizontal, 30)
                .padding(.vertical, 24)
                .frame(maxWidth: .infinity)
            }
            .disabled(isLoading)
        }
        // SwiftUI cancels this demo task when the screen disappears.
        .task(id: isLoading) {
            guard isLoading else { return }

            do {
                try await Task.sleep(nanoseconds: 800_000_000)
                try Task.checkCancellation()
            } catch {
                isLoading = false
                return
            }

            isLoading = false
            showSuccessAlert = true
        }
        .alert(
            "Demo Registration",
            isPresented: $showSuccessAlert
        ) {
            Button("Back to Sign In") {
                dismiss()
            }
        } message: {
            Text(
                "Your inputs are valid. Firebase account creation is not connected yet, so no account has been created."
            )
        }
    }

    // MARK: - Registration Validation
    private func registerAccount() {
        guard !isLoading else { return }

        errorMessage = nil

        let trimmedName = fullName.trimmingCharacters(
            in: .whitespacesAndNewlines
        )

        let trimmedEmail = email.trimmingCharacters(
            in: .whitespacesAndNewlines
        )

        // Check full name
        if trimmedName.count < 2 {
            errorMessage = "Please enter your full name."
            return
        }

        // Check email
        if trimmedEmail.isEmpty {
            errorMessage = "Please enter your email address."
            return
        }

        let emailPattern = #"^[A-Z0-9a-z._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"#

        if trimmedEmail.range(
            of: emailPattern,
            options: .regularExpression
        ) == nil {
            errorMessage = "Please enter a valid email address."
            return
        }

        // Check password
        if password.isEmpty {
            errorMessage = "Please enter a password."
            return
        }

        if password.count < 8 {
            errorMessage = "Password must contain at least 8 characters."
            return
        }

        if password.rangeOfCharacter(
            from: .uppercaseLetters
        ) == nil {
            errorMessage = "Password must contain an uppercase letter."
            return
        }

        if password.rangeOfCharacter(
            from: .lowercaseLetters
        ) == nil {
            errorMessage = "Password must contain a lowercase letter."
            return
        }

        if password.rangeOfCharacter(
            from: .decimalDigits
        ) == nil {
            errorMessage = "Password must contain a number."
            return
        }

        // Confirm password
        if confirmPassword.isEmpty {
            errorMessage = "Please confirm your password."
            return
        }

        if password != confirmPassword {
            errorMessage = "Passwords do not match."
            return
        }

        // MARK: - Mock Registration
        // Firebase will replace this section later.
        isLoading = true
    }
}

// MARK: - Preview
#Preview {
    NavigationStack {
        RegisterView()
    }
}
