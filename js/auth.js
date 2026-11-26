/* MOVA Firebase Authentication (compat SDK). */
(() => {
  const cfg = window.MOVA_FIREBASE_CONFIG;
  const pagePath = window.location.pathname;
  const inPages = /\/pages\//.test(pagePath);
  const loginUrl = `${inPages ? '' : 'pages/'}login.html`;
  const publicPages = ['index.html', 'discover.html', 'region-details.html', 'place-details.html', 'login.html'];
  const currentFile = pagePath.split('/').pop() || 'index.html';
  const protectedPages = ['profile.html'];

  function showMessage(message, kind = 'error') {
    const el = document.querySelector('[data-auth-message]');
    if (el) { el.textContent = message; el.dataset.kind = kind; el.hidden = false; }
  }
  function auth() { return window.firebase?.auth ? firebase.auth() : null; }
  function redirectToLogin() {
    const next = window.location.pathname + window.location.search + window.location.hash;
    window.location.href = `${loginUrl}?next=${encodeURIComponent(next)}`;
  }
  function safeNext() {
    const value = new URLSearchParams(location.search).get('next') || '';
    if (!value.startsWith('/') && !value.startsWith('pages/')) return '../index.html';
    if (value.startsWith('//') || value.includes('://')) return '../index.html';
    return value;
  }
  function resolveSignedInLabel(user) {
    if (!user) return '';
    try {
      const stored = JSON.parse(localStorage.getItem('movaProfile') || 'null');
      const username = String(stored?.username || '').trim();
      if (username) return `@${username}`;
      const profileName = String(stored?.displayName || '').trim();
      if (profileName) return profileName;
    } catch {}
    const displayName = String(user.displayName || '').trim();
    if (displayName) return displayName;
    const email = String(user.email || '').trim();
    return email ? email.split('@')[0] : '';
  }
  function updateSignedInUI(user) {
    const label = resolveSignedInLabel(user);
    document.querySelectorAll('[data-auth-status]').forEach(el => {
      el.textContent = label;
      el.hidden = !user || !label;
      if (label) el.title = label;
      else el.removeAttribute('title');
    });
    document.querySelectorAll('[data-sign-out]').forEach(el => { el.hidden = !user; });
    document.querySelectorAll('[data-sign-in]').forEach(el => { el.hidden = false; el.textContent = user ? 'PROFILE' : 'SIGN IN'; });
    document.documentElement.dataset.authState = user ? 'signed-in' : 'signed-out';
    window.dispatchEvent(new CustomEvent('mova:auth-state', { detail: { user } }));
  }
  async function start() {
    if (!window.firebase || !cfg) {
      if (protectedPages.includes(currentFile)) {
        document.body.innerHTML = '<main style="max-width:700px;margin:10vh auto;padding:24px;font-family:Arial"><h1>MOVA sign-in could not start</h1><p>Firebase SDK could not load. Check your internet connection and reload.</p><a href="../index.html">Return home</a></main>';
      }
      return;
    }
    if (!firebase.apps.length) firebase.initializeApp(cfg);
    const a = auth();
    try { await a.setPersistence(firebase.auth.Auth.Persistence.LOCAL); } catch (e) { console.warn('Firebase persistence unavailable', e); }
    a.onAuthStateChanged(user => {
      updateSignedInUI(user);
      if (protectedPages.includes(currentFile) && !user) redirectToLogin();
      if (currentFile === 'login.html' && user) location.replace(safeNext());
    });

    const form = document.querySelector('#auth-form');
    if (form) {
      const modeInput = form.querySelector('[name="authMode"]');
      // The sign-in/register mode buttons sit outside the form in login.html.
      // Bind them from the document, not from the form element.
      document.querySelectorAll('[data-auth-mode]').forEach(btn => btn.addEventListener('click', () => {
        modeInput.value = btn.dataset.authMode;
        form.querySelectorAll('[data-auth-mode]').forEach(b => b.classList.toggle('is-active', b === btn));
        const submit = form.querySelector('[type="submit"]');
        if (submit) submit.textContent = modeInput.value === 'register' ? 'CREATE ACCOUNT' : 'SIGN IN';
        const confirm = form.querySelector('[name="confirmPassword"]');
        if (confirm) confirm.closest('.auth-field').hidden = modeInput.value !== 'register';
        const displayName = form.querySelector('[name="displayName"]');
        if (displayName) displayName.closest('.auth-field').hidden = modeInput.value !== 'register';
        const message = document.querySelector('[data-auth-message]');
        if (message) { message.textContent = ''; message.hidden = true; }
      }));
      form.addEventListener('submit', async e => {
        e.preventDefault();
        const email = form.elements.email.value.trim();
        const password = form.elements.password.value;
        const mode = modeInput.value;
        const submit = form.querySelector('[type="submit"]');
        if (mode === 'register' && password !== form.elements.confirmPassword.value) return showMessage('Passwords do not match.');
        submit.disabled = true; submit.textContent = 'PLEASE WAIT…';
        try {
          if (mode === 'register') {
            const credential = await a.createUserWithEmailAndPassword(email, password);
            const displayName = form.elements.displayName.value.trim();
            if (displayName) await credential.user.updateProfile({ displayName });
          } else {
            await a.signInWithEmailAndPassword(email, password);
          }
          location.replace(safeNext());
        } catch (err) {
          const messages = {
            'auth/email-already-in-use': 'An account already exists for this email. Sign in instead.',
            'auth/invalid-email': 'Enter a valid email address.',
            'auth/weak-password': 'Choose a stronger password (at least 6 characters).',
            'auth/invalid-credential': 'Email or password is incorrect.',
            'auth/user-not-found': 'No account was found for this email.',
            'auth/wrong-password': 'Email or password is incorrect.',
            'auth/too-many-requests': 'Too many attempts. Wait a little and try again.'
          };
          showMessage(messages[err.code] || err.message || 'Authentication failed. Please try again.');
        } finally {
          submit.disabled = false; submit.textContent = mode === 'register' ? 'CREATE ACCOUNT' : 'SIGN IN';
        }
      });
      const google = document.querySelector('[data-google-sign-in]');
      if (google) google.addEventListener('click', async () => {
        try { await a.signInWithPopup(new firebase.auth.GoogleAuthProvider()); location.replace(safeNext()); }
        catch (err) { showMessage(err.message || 'Google sign-in failed.'); }
      });
      const reset = document.querySelector('[data-password-reset]');
      if (reset) reset.addEventListener('click', async () => {
        const email = form.elements.email.value.trim();
        if (!email) return showMessage('Enter your email first, then choose Forgot password.');
        try { await a.sendPasswordResetEmail(email); showMessage('Password reset email sent. Check your inbox.', 'success'); }
        catch (err) { showMessage(err.message || 'Could not send reset email.'); }
      });
    }

    document.addEventListener('click', async e => {
      const signOut = e.target.closest('[data-sign-out]');
      if (signOut) { e.preventDefault(); try { await a.signOut(); location.href = inPages ? '../index.html' : 'index.html'; } catch (err) { showMessage(err.message); } }
      const protectedAction = e.target.closest('[data-requires-auth], [data-action=\"like\"], [data-action=\"comment\"], [data-action=\"save\"], [data-action=\"plan\"], [data-action=\"delete\"]');
      if (protectedAction && !a.currentUser) { e.preventDefault(); e.stopImmediatePropagation(); redirectToLogin(); }
    }, true);
    document.addEventListener('submit', e => {
      const formEl = e.target;
      if (formEl.matches('[data-requires-auth]') && !a.currentUser) { e.preventDefault(); e.stopImmediatePropagation(); redirectToLogin(); }
    }, true);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
  window.movaGetFirebaseUser = () => auth()?.currentUser || null;
  window.movaGetIdToken = async () => { const user = auth()?.currentUser; return user ? user.getIdToken() : null; };
  window.movaRequireAuth = () => { if (auth()?.currentUser) return true; redirectToLogin(); return false; };
})();
