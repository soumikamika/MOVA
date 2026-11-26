# MOVA Firebase Authentication Setup

## Included
- Firebase email/password registration and sign-in
- Google popup sign-in (enable the Google provider in Firebase Authentication)
- Password reset email
- Public exploration pages remain public
- Explore, My Plans, Create Plan, Edit Plan, and Plan Dashboard are available without sign-in
- Profile requires sign-in; community publishing and comments also require sign-in
- Community browsing remains public; publishing and comments require sign-in in the UI
- Trip planning API endpoints are public so visitors can generate and edit plans without an account. Firebase Authentication remains available for account/profile features.

## Firebase console
1. In Firebase Console → Authentication → Sign-in method, enable Email/Password. Enable Google if you want Google sign-in.
2. In Authentication → Settings → Authorized domains, add the hostname used to serve MOVA (for local development, `localhost` and `127.0.0.1` as applicable).
3. Keep the web app configuration in `js/firebase-config.js`. It is client configuration, not a service-account private key.

## Backend verification (for future protected backend features)
1. Open Firebase Console → Project settings → Service accounts.
2. Generate a private key for the Firebase Admin SDK. Store the downloaded JSON outside this project folder; never commit or share it.
3. Install backend requirements in the MOVA backend virtual environment: `pip install -r requirements.txt`.
4. In the same terminal used to launch the backend, set `GOOGLE_APPLICATION_CREDENTIALS` to the absolute path of the service-account JSON. On Windows PowerShell: `$env:GOOGLE_APPLICATION_CREDENTIALS="C:\secure\mova-travel-admin.json"`. In Command Prompt: `set GOOGLE_APPLICATION_CREDENTIALS=C:\secure\mova-travel-admin.json`.
5. Start the backend from that same terminal. Protected plan endpoints intentionally reject requests until this credential is configured.

## Important
Trip planning is intentionally public in this version. Profile and community actions are gated in the frontend; add server-side Firebase token verification before introducing private profile APIs or user-owned cloud data. User profile data, plans and community persistence are still largely local-storage based in this prototype; Firebase Authentication establishes identity but does not automatically sync that data across devices.
