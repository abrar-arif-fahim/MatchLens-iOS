
import SwiftUI

struct LoginView: View {

    @State private var email = ""
    @State private var password = ""
    @State private var isPasswordVisible = false
    @State private var errorMessage: String? = nil
    

    var body: some View {
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
}

#Preview {
    LoginView()
}
