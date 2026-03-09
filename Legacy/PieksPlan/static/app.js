/* PieksPlan - JavaScript */

// Flash-Messages nach 5 Sekunden ausblenden
document.addEventListener('DOMContentLoaded', function() {
    const flashes = document.querySelectorAll('.flash');
    flashes.forEach(function(flash) {
        setTimeout(function() {
            flash.style.opacity = '0';
            flash.style.transform = 'translateY(-10px)';
            setTimeout(function() { flash.remove(); }, 300);
        }, 5000);
    });
});

// Bestaetigungsdialog fuer Loeschen
function confirmDelete(message) {
    return confirm(message || 'Sind Sie sicher, dass Sie diesen Eintrag loeschen moechten?');
}

// Freitext-Feld fuer Impfung ein-/ausblenden
function toggleFreitext() {
    var auswahl = document.getElementById('impftyp_auswahl');
    var freitextGroup = document.getElementById('freitext-group');
    var intervallGroup = document.getElementById('intervall-group');

    if (auswahl && freitextGroup) {
        if (auswahl.value === 'freitext') {
            freitextGroup.style.display = 'block';
            if (intervallGroup) intervallGroup.style.display = 'block';
        } else {
            freitextGroup.style.display = 'none';
            if (intervallGroup) intervallGroup.style.display = 'none';
        }
    }
}
