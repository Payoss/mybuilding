// ============================================================
// mybuilding.dev — Auth guard (include BEFORE any page content)
// ============================================================
(function() {
  var HASH = 'e1ab3c814d33d5c6588c5bd00d96b5bda179157650b9e3a32fb0b65ed305cf13';
  if (sessionStorage.getItem('mb_auth') !== HASH) {
    window.location.href = '/login.html?r=' + encodeURIComponent(window.location.pathname + window.location.search);
  }
})();
