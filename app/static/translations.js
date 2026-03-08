// static/js/translations.js
const translations = {
    fr: {
        'no_results_for': 'Aucun résultat pour',
        'artists': 'Artistes',
        'works': 'Œuvres',
        'museums': 'Musées',
        'cities': 'Villes',
        'countries': 'Pays'
    },
    en: {
        'no_results_for': 'No results for',
        'artists': 'Artists',
        'works': 'Works',
        'museums': 'Museums',
        'cities': 'Cities',
        'countries': 'Countries'
    }
};

function getCurrentLanguage() {
    return document.documentElement.lang || 'fr';
}

function t(key) {
    const lang = getCurrentLanguage();
    return translations[lang][key] || key;
}
