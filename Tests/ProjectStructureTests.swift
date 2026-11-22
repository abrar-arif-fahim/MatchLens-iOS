import Foundation

// Checks target wiring, not iOS/SDK compilation. Run from the repository root.
@main
struct ProjectStructureTests {
    static var checks = 0
    static func expect(_ value: @autoclosure () -> Bool, _ message: String) {
        precondition(value(), message); checks += 1
    }
    static func main() throws {
        let data = try Data(contentsOf: URL(fileURLWithPath: "MatchLens.xcodeproj/project.pbxproj"))
        let plist = try PropertyListSerialization.propertyList(from: data, options: [], format: nil) as! [String: Any]
        let objects = plist["objects"] as! [String: [String: Any]]
        let targets = objects.values.filter { $0["isa"] as? String == "PBXNativeTarget" }
        expect(targets.count == 1, "One native app target")
        let target = targets[0]
        expect(target["productType"] as? String == "com.apple.product-type.application", "Application product")
        let phases = target["buildPhases"] as! [String]
        let sourcePhase = phases.compactMap { objects[$0] }.first { $0["isa"] as? String == "PBXSourcesBuildPhase" }!
        let fileIDs = (sourcePhase["files"] as! [String]).map { objects[$0]!["fileRef"] as! String }
        expect(Set(fileIDs).count == fileIDs.count, "No duplicate compiled source references")
        let sourceNames = fileIDs.map { objects[$0]!["path"] as! String }
        let sourceFiles = FileManager.default.enumerator(atPath: "MatchLensApp")!.allObjects.compactMap { $0 as? String }.filter { $0.hasSuffix(".swift") }
        expect(Set(sourceNames) == Set(sourceFiles.map { URL(fileURLWithPath: $0).lastPathComponent }), "Every app Swift file belongs to the target")
        for name in sourceNames {
            expect(!name.hasSuffix("Tests.swift"), "Standalone test entry points excluded")
            expect(sourceFiles.filter { URL(fileURLWithPath: $0).lastPathComponent == name }.count == 1, "Unambiguous source filename")
        }
        let allAppSource = try sourceFiles.map { try String(contentsOfFile: "MatchLensApp/" + $0, encoding: .utf8) }.joined(separator: "\n")
        let entries = allAppSource.components(separatedBy: .newlines).filter { $0.trimmingCharacters(in: .whitespaces) == "@main" }
        expect(entries.count == 1, "One app entry point")
        expect(!allAppSource.contains("showDemoAlert") && !allAppSource.contains("showSuccessAlert"), "No demo-auth success paths")
        let products = (target["packageProductDependencies"] as! [String]).map { objects[$0]!["productName"] as! String }
        expect(Set(products) == ["FirebaseCore", "FirebaseAuth", "FirebaseFirestore"], "Only the needed Firebase products")
        let packages = objects.values.filter { $0["isa"] as? String == "XCRemoteSwiftPackageReference" }
        expect(packages.count == 1, "One Firebase package")
        let package = packages[0]
        expect(package["repositoryURL"] as? String == "https://github.com/firebase/firebase-ios-sdk", "Official SDK repository")
        let requirement = package["requirement"] as! [String: Any]
        expect(requirement["version"] as? String == "13.2.0" && requirement["kind"] as? String == "exactVersion", "Reviewed SDK version")
        let configurations = objects[target["buildConfigurationList"] as! String]!["buildConfigurations"] as! [String]
        for id in configurations {
            let settings = objects[id]!["buildSettings"] as! [String: Any]
            expect(settings["SDKROOT"] as? String == "iphoneos", "iOS SDK")
            expect(settings["SUPPORTED_PLATFORMS"] as? String == "iphoneos iphonesimulator", "Device/simulator support")
            expect(settings["INFOPLIST_KEY_FirebaseAppDelegateProxyEnabled"] as? String == "NO", "SwiftUI delegate integration")
        }
        let resourcePhase = phases.compactMap { objects[$0] }.first { $0["isa"] as? String == "PBXResourcesBuildPhase" }!
        let resources = (resourcePhase["files"] as! [String]).map { objects[objects[$0]!["fileRef"] as! String]!["path"] as! String }
        expect(resources.contains("Backend/input/competition_mappings.json"), "Reuse the existing reviewed catalog")
        expect(!resources.contains(where: { $0.contains(".env") || $0.contains("adminsdk") }), "No backend secrets as resources")
        print("Xcode project structure checks passed (\(checks) assertions). Native build remains pending.")
    }
}
