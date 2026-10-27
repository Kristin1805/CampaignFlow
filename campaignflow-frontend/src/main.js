import './styles/reset.css'
import './styles/variables.css'
import './styles/global.css'
import './styles/typography.css'
import './styles/components.css'
import {renderCurrentPage, navigateTo} from "./config/routes.js";

renderCurrentPage();
window.addEventListener('popstate', renderCurrentPage);
window.addEventListener('click', function(event) {
    const link = event.target.closest('a');
    if (!link) return;
    event.preventDefault();
    const path = link.getAttribute('href');
    navigateTo(path);
});
