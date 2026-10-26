import {renderDashboardPage} from "../pages/dashboard/dashboard-page.js";
import {renderNotFoundPage} from "../pages/not-found/not-found-page.js";

export const routes = {'/' : renderDashboardPage};

export function renderCurrentPage() {
    const path = window.location.pathname
    const pageFunction = routes[path] ?? renderNotFoundPage
    document.querySelector('#app').innerHTML = pageFunction()

}