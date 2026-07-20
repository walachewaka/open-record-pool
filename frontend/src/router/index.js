import { createRouter, createWebHistory } from 'vue-router';

import store from '@/store';

import Account from '@/views/Account';
import AdminAudit from '@/views/admin/AdminAudit';
import AdminContent from '@/views/admin/AdminContent';
import AdminDashboard from '@/views/admin/AdminDashboard';
import AdminDownloads from '@/views/admin/AdminDownloads';
import AdminDuplicates from '@/views/admin/AdminDuplicates';
import AdminEnrichment from '@/views/admin/AdminEnrichment';
import AdminModeration from '@/views/admin/AdminModeration';
import AdminReports from '@/views/admin/AdminReports';
import AdminRoles from '@/views/admin/AdminRoles';
import AdminSettings from '@/views/admin/AdminSettings';
import AdminSongRequests from '@/views/admin/AdminSongRequests';
import AdminTelemetry from '@/views/admin/AdminTelemetry';
import AdminUsers from '@/views/admin/AdminUsers';
import ArtistDetail from '@/views/ArtistDetail';
import Artists from '@/views/Artists';
import Browse from '@/views/Browse';
import Charts from '@/views/Charts';
import CrateView from '@/views/CrateView';
import Dashboard from '@/views/Dashboard';
import Downloads from '@/views/Downloads';
import EditNote from '@/views/EditNote';
import Genres from '@/views/Genres';
import Home from '@/views/Home.vue';
import HomeDashboard from '@/views/HomeDashboard.vue';
import Login from '@/views/Login';
import Note from '@/views/Note';
import PublicCrates from '@/views/PublicCrates';
import Register from '@/views/Register';
import Release from '@/views/Release';
import Releases from '@/views/Releases';
import Requests from '@/views/Requests';
import Search from '@/views/Search';

// Every route belongs to an `area` (member | admin, default member); the
// shell switches the sidebar variant on it and only shows the player bar in
// the member area. `title`/`subtitle` feed the topbar heading.
const routes = [
  {
    path: '/',
    name: "Home",
    component: Home,
    meta: {title: 'Home', subtitle: 'Self-hosted record pool'},
    // Members land on the Home dashboard (MOO-94); the legacy public page
    // stays for logged-out visitors.
    beforeEnter: (to, from, next) => {
      if (store.getters.isAuthenticated) {
        next('/home');
      } else {
        next();
      }
    },
  },
  {
    path: '/home',
    name: 'HomeDashboard',
    component: HomeDashboard,
    meta: {requiresAuth: true, title: 'Home', subtitle: 'Your pool at a glance'},
  },
  {
    path: '/register',
    name: 'Register',
    component: Register,
    meta: {title: 'Register', subtitle: 'Create a member account'},
  },
  {
    path: '/login',
    name: 'Login',
    component: Login,
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: Dashboard,
    meta: {requiresAuth: true, title: 'Notes', subtitle: 'Your shared notes'},
  },
  {
    path: '/profile',
    name: 'Account',
    component: Account,
    meta: {requiresAuth: true, title: 'Account', subtitle: 'Membership & profile'},
  },
  {
    path: '/library',
    name: 'Browse',
    component: Browse,
    meta: {requiresAuth: true, title: 'New Releases', subtitle: 'Fresh additions to the pool'},
  },
  {
    path: '/release/:id',
    name: 'Release',
    component: Release,
    meta: {requiresAuth: true, title: 'Release', subtitle: 'Release detail'},
  },
  {
    path: '/crate/shared/:token',
    name: 'SharedCrate',
    component: CrateView,
    props: {shared: true},
    meta: {requiresAuth: true, title: 'Shared crate', subtitle: 'A set shared with you'},
  },
  {
    path: '/crate/:id(\\d+)',
    name: 'Crate',
    component: CrateView,
    meta: {requiresAuth: true, title: 'Crates', subtitle: 'Build and share your sets'},
  },
  {
    path: '/crates/discover',
    name: 'PublicCrates',
    component: PublicCrates,
    meta: {requiresAuth: true, title: 'Public Crates', subtitle: 'Sets shared by the community'},
  },
  {
    path: '/genres',
    name: 'Genres',
    component: Genres,
    meta: {requiresAuth: true, title: 'Genres', subtitle: 'Browse the pool by genre'},
  },
  {
    path: '/charts',
    name: 'Charts',
    component: Charts,
    meta: {requiresAuth: true, title: 'Charts', subtitle: 'Most downloaded & most played'},
  },
  {
    path: '/search',
    name: 'Search',
    component: Search,
    meta: {requiresAuth: true, title: 'Search', subtitle: 'Find tracks across the pool'},
  },
  {
    path: '/downloads',
    name: 'Downloads',
    component: Downloads,
    meta: {requiresAuth: true, title: 'Downloads', subtitle: 'Your download history'},
  },
  {
    path: '/requests',
    name: 'Requests',
    component: Requests,
    meta: {requiresAuth: true, title: 'Requests', subtitle: 'Ask for tracks the pool is missing'},
  },
  {
    path: '/artists',
    name: 'Artists',
    component: Artists,
    meta: {requiresAuth: true, title: 'Artists', subtitle: 'Follow artists to track releases'},
  },
  {
    path: '/artist/:id',
    name: 'ArtistDetail',
    component: ArtistDetail,
    meta: {requiresAuth: true, title: 'Artist', subtitle: 'Library tracks & releases'},
  },
  {
    path: '/releases',
    name: 'Releases',
    component: Releases,
    meta: {
      requiresAuth: true,
      title: 'Release Radar',
      subtitle: 'Upcoming & new releases from artists you follow',
    },
  },
  {
    path: '/admin',
    name: 'AdminDashboard',
    component: AdminDashboard,
    meta: {
      requiresAuth: true,
      area: 'admin',
      permission: 'view_reports',
      title: 'Dashboard',
      subtitle: 'Pool overview & health',
    },
  },
  {
    path: '/admin/users',
    name: 'AdminUsers',
    component: AdminUsers,
    meta: {
      requiresAuth: true,
      area: 'admin',
      permission: 'manage_users',
      title: 'Users',
      subtitle: 'Members & access',
    },
  },
  {
    path: '/admin/content',
    name: 'AdminContent',
    component: AdminContent,
    meta: {
      requiresAuth: true,
      area: 'admin',
      permission: 'edit_metadata',
      title: 'Content',
      subtitle: 'Catalog & uploads',
    },
  },
  {
    path: '/admin/duplicates',
    name: 'AdminDuplicates',
    component: AdminDuplicates,
    meta: {
      requiresAuth: true,
      area: 'admin',
      permission: 'edit_metadata',
      title: 'Duplicates',
      subtitle: 'One canonical version per recording',
    },
  },
  {
    path: '/admin/enrichment',
    name: 'AdminEnrichment',
    component: AdminEnrichment,
    meta: {
      requiresAuth: true,
      area: 'admin',
      permission: 'edit_metadata',
      title: 'Enrichment',
      subtitle: 'Beatport metadata matching & review',
    },
  },
  {
    path: '/admin/moderation',
    name: 'AdminModeration',
    component: AdminModeration,
    meta: {
      requiresAuth: true,
      area: 'admin',
      permission: 'approve_submissions',
      title: 'Moderation',
      subtitle: 'Submission queue',
    },
  },
  {
    path: '/admin/requests',
    name: 'AdminSongRequests',
    component: AdminSongRequests,
    meta: {
      requiresAuth: true,
      area: 'admin',
      permission: 'approve_submissions',
      title: 'Requests',
      subtitle: 'Member song requests',
    },
  },
  {
    path: '/admin/roles',
    name: 'AdminRoles',
    component: AdminRoles,
    meta: {
      requiresAuth: true,
      area: 'admin',
      permission: 'manage_roles',
      title: 'Roles & Permissions',
      subtitle: 'What each role can do',
    },
  },
  {
    path: '/admin/reports',
    name: 'AdminReports',
    component: AdminReports,
    meta: {
      requiresAuth: true,
      area: 'admin',
      permission: 'view_reports',
      title: 'Reports',
      subtitle: 'Downloads & catalog analytics',
    },
  },
  {
    path: '/admin/insights',
    name: 'AdminTelemetry',
    component: AdminTelemetry,
    meta: {
      requiresAuth: true,
      area: 'admin',
      permission: 'view_reports',
      title: 'Insights',
      subtitle: 'Telemetry & dashboards',
    },
  },
  {
    path: '/admin/audit',
    name: 'AdminAudit',
    component: AdminAudit,
    meta: {
      requiresAuth: true,
      area: 'admin',
      permission: 'view_reports',
      title: 'Audit log',
      subtitle: 'Security events',
    },
  },
  {
    path: '/admin/downloads',
    name: 'AdminDownloads',
    component: AdminDownloads,
    meta: {
      requiresAuth: true,
      area: 'admin',
      permission: 'view_reports',
      title: 'Downloads',
      subtitle: 'Fetch engine queue',
    },
  },
  {
    path: '/admin/settings',
    name: 'AdminSettings',
    component: AdminSettings,
    meta: {
      requiresAuth: true,
      area: 'admin',
      permission: 'site_settings',
      title: 'Settings',
      subtitle: 'Instance configuration',
    },
  },
  {
    path: '/note/:id',
    name: 'Note',
    component: Note,
    meta: {requiresAuth: true, title: 'Notes', subtitle: 'Your shared notes'},
    props: true,
  },
  {
    path: '/editnote/:id',
    name: 'EditNote',
    component: EditNote,
    meta: {requiresAuth: true, title: 'Notes', subtitle: 'Your shared notes'},
    props: true,
  }
]

const router = createRouter({
  history: createWebHistory(process.env.BASE_URL),
  routes,
});

// The first admin view the user's permissions allow, so a partial admin (e.g.
// a curator without view_reports) landing on /admin is sent somewhere useful.
export function firstAdminPath(permissions) {
  const entry = routes.find(
    route => route.meta && route.meta.permission && permissions[route.meta.permission]
  );
  return entry ? entry.path : null;
}

router.beforeEach(async (to, from, next) => {
  if (!to.matched.some(record => record.meta.requiresAuth)) {
    next();
    return;
  }
  if (!store.getters.isAuthenticated) {
    next('/login');
    return;
  }
  const permission = to.meta.permission;
  if (permission) {
    // Sessions persisted before MOO-72 carry no permissions — refresh once
    // so a page reload straight into /admin doesn't bounce to the library.
    if (!store.getters.stateUser.permissions) {
      try {
        await store.dispatch('viewMe');
      } catch (error) {
        next('/login');
        return;
      }
    }
    if (!store.getters.userPermissions[permission]) {
      const fallback = firstAdminPath(store.getters.userPermissions);
      next(fallback && fallback !== to.path ? fallback : '/library');
      return;
    }
  }
  next();
});

export default router;
