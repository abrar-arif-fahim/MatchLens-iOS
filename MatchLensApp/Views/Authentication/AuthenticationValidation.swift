import Foundation

// A local format check for ordinary email addresses; it does not verify an account.
enum AuthenticationValidation {
    static func isValidEmail(_ value: String) -> Bool {
        let email = value.trimmingCharacters(in: .whitespacesAndNewlines)
        let parts = email.split(separator: "@", omittingEmptySubsequences: false)
        guard parts.count == 2 else { return false }
        let local = parts[0]
        guard !local.isEmpty, !local.hasPrefix("."), !local.hasSuffix("."),
              !local.contains("..") else { return false }

        // Domain labels start/end with a letter or digit; hyphens may be inside.
        // Require a dotted domain, keeping the existing app's basic email policy.
        let pattern = #"^[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"#
        return email.range(of: pattern, options: .regularExpression) != nil
    }
}
