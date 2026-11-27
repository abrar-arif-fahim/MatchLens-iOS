import UIKit
import FirebaseCore
import FirebaseAuth
import FirebaseFirestore

@MainActor
final class MatchLensAppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        FirebaseSetup.configure()
        return true
    }
}

@MainActor
enum FirebaseSetup {
    private(set) static var message: String?
    static func configure() {
        guard FirebaseApp.app() == nil else { return }
        guard let path = Bundle.main.path(forResource: "GoogleService-Info", ofType: "plist"),
              let options = FirebaseOptions(contentsOfFile: path),
              options.bundleID == Bundle.main.bundleIdentifier,
              let projectID = options.projectID, !projectID.isEmpty else {
            message = "Add the Firebase iOS GoogleService-Info.plist to the MatchLens app target, using its registered bundle identifier. See Docs/NATIVE_FIREBASE_SETUP.md."
            return
        }
        // Configure only the public iOS client options, never an Admin service account.
        FirebaseApp.configure(options: options)
        let db = Firestore.firestore()
        let settings = db.settings
        settings.cacheSettings = MemoryCacheSettings()
        db.settings = settings
    }
    static func catalog() throws -> CompetitionBindings {
        guard let url = Bundle.main.url(forResource: "competition_mappings", withExtension: "json"),
              let data = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any] else {
            throw ClientError.invalidData("bundled competition mappings")
        }
        return try CompetitionBindings(data: data)
    }
    static func safeMessage(_ error: Error) -> String {
        if let error = error as? ClientError { return error.localizedDescription }
        let value = error as NSError
        if value.domain == ClientError.errorDomain {
            switch value.code {
            case 2: return ClientError.missingRecord.localizedDescription
            case 3: return ClientError.signedOut.localizedDescription
            case 4: return ClientError.conflict.localizedDescription
            case 5: return ClientError.mediaUnavailable.localizedDescription
            default: return ClientError.invalidData("stored information").localizedDescription
            }
        }
        if value.domain == AuthErrorDomain {
            switch AuthErrorCode(rawValue: value.code) {
            case .invalidCredential, .wrongPassword, .userNotFound: return "Email or password is incorrect."
            case .invalidEmail: return "Enter a valid email address."
            case .weakPassword: return "Choose a stronger password."
            case .emailAlreadyInUse: return "Unable to create the account. Try signing in or resetting your password."
            case .userDisabled: return "Sign-in is unavailable for this account."
            case .tooManyRequests: return "Too many attempts. Please try again later."
            case .networkError: return "Unable to connect. Check your connection."
            case .operationNotAllowed: return "Email sign-in is currently unavailable. Please contact support."
            default: return "Authentication could not finish. Please retry."
            }
        }
        if value.domain == FirestoreErrorDomain {
            switch FirestoreErrorCode.Code(rawValue: value.code) {
            case .permissionDenied: return "Your account doesn’t have access to this information."
            case .unauthenticated: return "Your session expired. Please sign in again."
            case .failedPrecondition: return "This information isn’t available right now. Please try again later."
            case .unavailable, .deadlineExceeded: return "Couldn’t connect. Check your internet connection and try again."
            default: break
            }
        }
        return "Unable to finish this operation. Check your connection and retry."
    }
}
