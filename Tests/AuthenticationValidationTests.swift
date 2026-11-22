import Foundation

// Compile with AuthenticationValidation.swift as a standalone test executable.
// Keep this file out of the app target: it has its own test entry point.
@main
struct AuthenticationValidationTests {
    static func main() {
        let valid = [
            "fan@example.com", "FAN@EXAMPLE.COM", "fan+match@example.co.uk",
            "fan.name@match-lens.example", "  fan@example.com\n", "fan@a.io"
        ]
        let invalid = [
            "", "   ", "fan", "@example.com", "fan@", "fan@@example.com",
            "fan@example", "fan@example..com", "fan@-example.com", "fan@example-.com",
            ".fan@example.com", "fan.@example.com", "fan..name@example.com",
            "fan name@example.com", "fan@exa mple.com", "fan@example.com.evil/route",
            "fan@" + String(repeating: "a", count: 64) + ".com"
        ]
        for email in valid {
            precondition(AuthenticationValidation.isValidEmail(email), "Valid demo email rejected")
        }
        for email in invalid {
            precondition(!AuthenticationValidation.isValidEmail(email), "Invalid demo email accepted")
        }
        print("Authentication validation checks passed (\(valid.count + invalid.count) cases).")
    }
}
