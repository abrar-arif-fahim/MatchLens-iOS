# MatchLens-iOS
Interactive football highlights and match analysis iOS application

Open `MatchLens.xcodeproj` in Xcode on a Mac to build the native iOS app. Select
the **MatchLens** scheme and an **iPhone simulator** running iOS 17 or later.
See [iOS setup](Docs/IOS_SETUP.md) for simulator installation, signing and build commands.

The backend includes an offline application workflow and Firebase client data
contracts. See [backend/iOS integration readiness](Docs/IOS_BACKEND_INTEGRATION.md)
for services, draft access rules and remaining live-integration work.

~~~powershell
python -B Backend/preview_app_workflow.py
python -B -m unittest discover -s Backend -p "test_*.py" -q
~~~

These commands use fictional match data and local snapshots; they do not log in,
request provider data or write to Firestore.

Native authentication and Firestore integration source is now included. Follow
[the Mac/Firebase setup instructions](Docs/NATIVE_FIREBASE_SETUP.md) before running.
The Firebase client plist and a successful Xcode build are still required;
Windows syntax/contract checks do not establish simulator readiness.
