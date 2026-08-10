const {themes: prismThemes} = require('prism-react-renderer');

const siteUrl = process.env.DOCUSAURUS_URL || 'https://proofofwork-agency.github.io';
const baseUrl = process.env.DOCUSAURUS_BASE_URL || '/engine/';
const showGitLastUpdate = process.env.GITHUB_ACTIONS === 'true';

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'Engine',
  tagline: 'From human intent to bounded, typed, and auditable actions',
  favicon: 'img/engine-mark.svg',
  url: siteUrl,
  baseUrl,
  organizationName: 'proofofwork-agency',
  projectName: 'engine',
  deploymentBranch: 'gh-pages',
  trailingSlash: false,
  onBrokenLinks: 'throw',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
    localeConfigs: {
      en: {
        label: 'English',
        htmlLang: 'en-US',
      },
    },
  },

  markdown: {
    mermaid: true,
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    },
  },
  themes: ['@docusaurus/theme-mermaid'],

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: require.resolve('./sidebars.js'),
          routeBasePath: 'docs',
          showLastUpdateAuthor: showGitLastUpdate,
          showLastUpdateTime: showGitLastUpdate,
          editUrl: 'https://github.com/proofofwork-agency/engine/edit/main/docs-site/',
        },
        blog: false,
        theme: {
          customCss: require.resolve('./src/css/custom.css'),
        },
      },
    ],
  ],

  themeConfig: {
    image: 'img/engine-social-card.svg',
    colorMode: {
      defaultMode: 'dark',
      respectPrefersColorScheme: true,
    },
    metadata: [
      {
        name: 'description',
        content:
          'Engine is a local-first runtime for bounded, typed, and auditable actions across software and physical systems.',
      },
      {name: 'theme-color', content: '#0a1118'},
    ],
    navbar: {
      title: 'ENGINE',
      logo: {
        alt: 'Engine mark',
        src: 'img/engine-mark.svg',
      },
      hideOnScroll: true,
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'mainSidebar',
          position: 'left',
          label: 'Documentation',
        },
        {
          href: 'https://github.com/proofofwork-agency/engine',
          label: 'GitHub',
          position: 'right',
          className: 'navbar-github-link',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Engine',
          items: [
            {label: 'Documentation', to: '/docs/concepts/what-is-engine'},
            {label: 'GitHub', href: 'https://github.com/proofofwork-agency/engine'},
          ],
        },
        {
          title: 'Invariants',
          items: [
            {
              html: '<span>LLM-proposal ≠ authority</span>',
            },
            {
              html: '<span>Prediction ≠ observation</span>',
            },
          ],
        },
      ],
      copyright: `Engine — experimental research · ${new Date().getFullYear()}`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'json'],
    },
  },
};

module.exports = config;
