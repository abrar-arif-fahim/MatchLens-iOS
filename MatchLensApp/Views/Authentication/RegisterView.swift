import SwiftUI

struct RegisterView: View {
    @EnvironmentObject private var app: AppStore
    @Environment(\.dismiss) private var dismiss
    @State private var fullName = ""
    @State private var email = ""
    @State private var password = ""
    @State private var confirmPassword = ""
    @State private var isPasswordVisible = false
    @State private var isConfirmPasswordVisible = false
    private var isLoading: Bool { app.authBusy }
    @State private var errorMessage: String?
    @FocusState private var focusedField: Field?

    private enum Field: Hashable {
        case name, email, password, confirmation
    }

    private let background = Color(red: 11 / 255, green: 15 / 255, blue: 31 / 255)
    private let fieldBackground = Color(red: 26 / 255, green: 38 / 255, blue: 58 / 255)
    private let secondaryText = Color(red: 166 / 255, green: 185 / 255, blue: 209 / 255)
    private let accent = Color(red: 41 / 255, green: 119 / 255, blue: 250 / 255)

    var body: some View {
        ZStack {
            background.ignoresSafeArea()

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

                        Text("Create Account")
                            .font(.system(size: 30, weight: .bold))
                            .foregroundColor(Color(red: 240 / 255, green: 243 / 255, blue: 251 / 255))
                            .accessibilityAddTraits(.isHeader)

                        Text("Create an account to save every moment.")
                            .font(.system(size: 14))
                            .foregroundColor(secondaryText)
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
                            .autocorrectionDisabled()
                            .focused($focusedField, equals: .name)
                            .submitLabel(.next)
                            .onSubmit { focusedField = .email }
                            .disabled(isLoading)
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
                            .focused($focusedField, equals: .email)
                            .submitLabel(.next)
                            .onSubmit { focusedField = .password }
                            .disabled(isLoading)
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
                            .focused($focusedField, equals: .password)
                            .submitLabel(.next)
                            .onSubmit { focusedField = .confirmation }
                            .disabled(isLoading)
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
                            .focused($focusedField, equals: .confirmation)
                            .submitLabel(.done)
                            .onSubmit { registerAccount() }
                            .disabled(isLoading)
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
                            .accessibilityLabel("Registration error: \(errorMessage)")
                    }
                    if let error = app.errorMessage {
                        Text(error).font(.system(size: 14)).foregroundStyle(.red)
                    }

                    // MARK: - Create Account Button
                    Button {
                        registerAccount()
                    } label: {

                        HStack(spacing: 10) {

                            if isLoading {
                                ProgressView()
                                    .tint(.white)
                            } else {
                                Text("Create Account")
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
                            Text("Sign in")
                                .font(.system(size: 14))
                                .foregroundColor(secondaryText)
                                .frame(maxWidth: .infinity, minHeight: 44)
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityHint("Returns to the sign-in screen")
                        .disabled(isLoading)
                    }
                    .padding(.top, 74)
                }
                .frame(maxWidth: 440)
                .padding(.horizontal, 24)
                .padding(.top, 58)
                .padding(.bottom, 40)
                .frame(maxWidth: .infinity)
            }
            .scrollDismissesKeyboard(.interactively)
        }
        .tint(accent)
        .preferredColorScheme(.dark)
        .navigationBarBackButtonHidden(true)
        .toolbar(.hidden, for: .navigationBar)
        .onAppear { app.errorMessage = nil }
    }

    // MARK: - Registration Validation
    private func registerAccount() {
        guard !isLoading else { return }
        errorMessage = nil

        let submittedName = fullName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard (2...80).contains(submittedName.count),
              (try? DocumentFields(data: ["displayName": submittedName]).text("displayName")) != nil else {
            errorMessage = "Please enter your full name."
            focusedField = .name
            return
        }

        let trimmedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
        guard AuthenticationValidation.isValidEmail(trimmedEmail) else {
            errorMessage = "Please enter a valid email address."
            focusedField = .email
            return
        }

        // Preserve the existing project's password requirements.
        guard password.count >= 8,
              password.rangeOfCharacter(from: .uppercaseLetters) != nil,
              password.rangeOfCharacter(from: .lowercaseLetters) != nil,
              password.rangeOfCharacter(from: .decimalDigits) != nil else {
            errorMessage = "Use at least 8 characters, including uppercase, lowercase and a number."
            focusedField = .password
            return
        }

        guard !confirmPassword.isEmpty, password == confirmPassword else {
            errorMessage = "Passwords do not match."
            focusedField = .confirmation
            return
        }

        focusedField = nil
        let submittedPassword = password
        Task {
            await app.register(name: submittedName, email: trimmedEmail, password: submittedPassword)
            password = ""; confirmPassword = ""
        }
    }
}

#Preview {
    NavigationStack {
        RegisterView()
    }
    .environmentObject(AppStore())
}
