import {renderDashboardPage} from "../pages/dashboard/dashboard-page.js";
import {renderNotFoundPage} from "../pages/not-found/not-found-page.js";
import {renderCampaignsPage} from "../pages/campaigns/campaigns-page.js";
import {renderSidebar} from "../components/navigation/sidebar.js";

export const routes = {
    '/' : renderDashboardPage,
    '/campaigns': renderCampaignsPage
};

export function renderCurrentPage() {
    const path = window.location.pathname
    const pageFunction = routes[path] ?? renderNotFoundPage
    document.querySelector('#app').innerHTML = renderSidebar() + pageFunction();

}

export function navigateTo(path){
    history.pushState(null, '', path);
    renderCurrentPage();
}

