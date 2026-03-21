// ============================================================
// mybuilding.dev — Auth guard (include BEFORE any page content)
// ============================================================
(function() {
  var HASH = 'ffb56b8d39faa60b53c15957c255c08e977b6fbe96c4ce9dcf1214bf48b91bc2';
  if (sessionStorage.getItem('mb_auth') !== HASH) {
    window.location.href = '/login.html?r=' + encodeURIComponent(window.location.pathname + window.location.search);
  }
})();
