import SwiftUI

struct RegisterView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var fullName = ""
    @State private var email = ""
    @State private var password = ""
    @State private var confirmPassword = ""
    @State private var errorMessage: String?
    @State private var showSuccessAlert = false
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
                VStack(alignment: .leading, spacing: 0) {
                    VStack(alignment: .leading, spacing: 14) {
                        Text("Join MatchLens")
                            .font(.system(size: 30, weight: .bold))
                            .foregroundColor(Color(red: 240 / 255, green: 243 / 255, blue: 251 / 255))
                            .accessibilityAddTraits(.isHeader)

                        Text("Create an account to save every moment.")
                            .font(.system(size: 14))
                            .foregroundColor(secondaryText)
                    }
                    .padding(.horizontal, 5)

                    VStack(spacing: 20) {
                        inputStyle(
                            TextField("Full name", text: $fullName, prompt: placeholder("Full name"))
                                .textContentType(.name)
                                .textInputAutocapitalization(.words)
                                .focused($focusedField, equals: .name)
                                .submitLabel(.next)
                                .onSubmit { focusedField = .email }
                        )

                        inputStyle(
                            TextField("Email address", text: $email, prompt: placeholder("Email address"))
                                .keyboardType(.emailAddress)
                                .textContentType(.emailAddress)
                                .textInputAutocapitalization(.never)
                                .focused($focusedField, equals: .email)
                                .submitLabel(.next)
                                .onSubmit { focusedField = .password }
                        )

                        inputStyle(
                            SecureField("Password", text: $password, prompt: placeholder("Password"))
                                .textContentType(.newPassword)
                                .focused($focusedField, equals: .password)
                                .submitLabel(.next)
                                .onSubmit { focusedField = .confirmation }
                        )

                        inputStyle(
                            SecureField("Confirm password", text: $confirmPassword, prompt: placeholder("Confirm password"))
                                .textContentType(.newPassword)
                                .focused($focusedField, equals: .confirmation)
                                .submitLabel(.done)
                                .onSubmit { registerAccount() }
                        )
                    }
                    .padding(.horizontal, 5)
                    .padding(.top, 54)

                    VStack(alignment: .leading, spacing: 16) {
                        if let errorMessage = errorMessage {
                            Text(errorMessage)
                                .font(.system(size: 14))
                                .foregroundColor(.red)
                                .accessibilityLabel("Registration error: \(errorMessage)")
                        }

                        Button(action: registerAccount) {
                            Text("Create account")
                                .font(.system(size: 16, weight: .bold))
                                .foregroundColor(.white)
                                .padding(.horizontal, 30)
                                .frame(maxWidth: .infinity, minHeight: 50, alignment: .leading)
                                .background(accent)
                                .clipShape(RoundedRectangle(cornerRadius: 18))
                        }
                        .buttonStyle(.plain)

                        Button {
                            dismiss()
                        } label: {
                            Text("Already registered? Sign in")
                                .font(.system(size: 14))
                                .foregroundColor(secondaryText)
                                .frame(maxWidth: .infinity, minHeight: 44)
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityHint("Returns to the sign-in screen")
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
        .alert("Demo registration complete", isPresented: $showSuccessAlert) {
            Button("Back to Sign in") { dismiss() }
        } message: {
            Text("Your details passed validation. No account has been created or saved.")
        }
    }

    private func placeholder(_ title: String) -> Text {
        Text(title).foregroundColor(secondaryText)
    }

    private func inputStyle<Content: View>(_ content: Content) -> some View {
        content
            .font(.system(size: 14))
            .foregroundColor(.white)
            .autocorrectionDisabled()
            .padding(.horizontal, 16)
            .frame(minHeight: 58)
            .background(fieldBackground)
            .clipShape(RoundedRectangle(cornerRadius: 17))
    }

    // Local validation only; no account data is sent or persisted.
    private func registerAccount() {
        errorMessage = nil

        guard fullName.trimmingCharacters(in: .whitespacesAndNewlines).count >= 2 else {
            errorMessage = "Please enter your full name."
            focusedField = .name
            return
        }

        let trimmedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
        let emailPattern = #"^[A-Z0-9a-z._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"#
        guard trimmedEmail.range(of: emailPattern, options: .regularExpression) != nil else {
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
        showSuccessAlert = true
    }
}

#Preview {
    NavigationStack {
        RegisterView()
    }
}
