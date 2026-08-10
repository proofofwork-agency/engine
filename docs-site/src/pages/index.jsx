import React from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import styles from './index.module.css';

const lifecycle = [
  'Observe',
  'Propose',
  'Validate',
  'Policy',
  'Authorize',
  'Dispatch',
  'Execute',
  'Observe',
  'Reconcile',
  'Record',
];

const operatingModes = [
  {
    index: '01',
    title: 'Deterministisch',
    text: 'Eén general executive werkt met vaste logica. CLI en SDK leveren intentie; policy houdt de autoriteitsgrens in stand.',
  },
  {
    index: '02',
    title: 'Model-backed',
    text: 'Eén general executive gebruikt een model voor deliberatie en voorstellen. Policy beslist of een actie bevoegd is.',
  },
  {
    index: '03',
    title: 'Meerdere specialisten',
    text: 'Nul of meer gespecialiseerde brains ondersteunen de general executive. Ze adviseren binnen scope en krijgen geen uitvoeringsrecht.',
  },
];

function Architecture() {
  return (
    <section className={styles.architecture} aria-labelledby="architecture-title">
      <div className={styles.sectionIntro}>
        <span className={styles.eyebrow}>Systeemgrenzen</span>
        <Heading as="h2" id="architecture-title">
          Denken en doen blijven bewust gescheiden.
        </Heading>
        <p>
          Engine koppelt precies één general executive — eventueel geholpen door specialisten — aan
          een deterministische uitvoeringskern. Geen enkele brain krijgt een geheime route naar een
          target.
        </p>
      </div>

      <div className={styles.systemMap}>
        <article className={clsx(styles.systemNode, styles.brainNode)}>
          <div className={styles.nodeHeader}>
            <span className={styles.nodeCode}>GENERAL EXECUTIVE / EXACTLY ONE</span>
            <span className={styles.nodePulse} aria-hidden="true" />
          </div>
          <Heading as="h3">Voorstellen & plannen</Heading>
          <p>Deterministische logica of model-backed brain, met optionele specialisten.</p>
          <span className={styles.nodeOutput}>OUTPUT · ProposedAction</span>
        </article>

        <div className={styles.policyGate} aria-label="Onafhankelijke policy- en autorisatiegrens">
          <span>SCHEMA</span>
          <strong>POLICY GATE</strong>
          <span>AUTHORIZATION</span>
        </div>

        <article className={clsx(styles.systemNode, styles.heartNode)}>
          <div className={styles.nodeHeader}>
            <span className={styles.nodeCode}>HEART / DURABLE STATE</span>
            <span className={styles.nodePulse} aria-hidden="true" />
          </div>
          <Heading as="h3">Coördinatie & registratie</Heading>
          <p>Typed state, validatie, lifecycle, receipts, effecten en herstel.</p>
          <span className={styles.nodeOutput}>OUTPUT · ExecutionReceipt</span>
        </article>

        <div className={styles.pluginRail}>
          <span className={styles.railLabel}>PLUGIN INTERFACE</span>
          <span>Capabilities</span>
          <span>Providers</span>
          <span>Controllers</span>
          <span>Oracles</span>
        </div>

        <div className={styles.targets} aria-label="Voorbeeldtargets">
          <span>FILESYSTEM</span>
          <span>WAREHOUSE</span>
          <span>CONTEXT</span>
          <span>HOMEY</span>
        </div>
      </div>
    </section>
  );
}

function Lifecycle() {
  return (
    <section className={styles.lifecycleSection} aria-labelledby="lifecycle-title">
      <div className={styles.sectionIntro}>
        <span className={styles.eyebrow}>Eén controleerbare keten</span>
        <Heading as="h2" id="lifecycle-title">
          Iedere mutatie laat bewijs achter.
        </Heading>
      </div>
      <ol className={styles.lifecycle}>
        {lifecycle.map((step, index) => (
          <li key={`${step}-${index}`}>
            <span>{String(index + 1).padStart(2, '0')}</span>
            <strong>{step}</strong>
          </li>
        ))}
      </ol>
      <p className={styles.lifecycleNote}>
        Ontbrekende telemetrie is <strong>UNKNOWN</strong>, niet automatisch mislukt of geslaagd.
      </p>
    </section>
  );
}

function Modes() {
  return (
    <section className={styles.modes} aria-labelledby="modes-title">
      <div className={styles.sectionIntro}>
        <span className={styles.eyebrow}>Samenstelling</span>
        <Heading as="h2" id="modes-title">
          Elk Heart heeft precies één general executive.
        </Heading>
      </div>
      <div className={styles.modeGrid}>
        {operatingModes.map((mode) => (
          <article key={mode.index} className={styles.modeCard}>
            <span>{mode.index}</span>
            <Heading as="h3">{mode.title}</Heading>
            <p>{mode.text}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function Home() {
  return (
    <Layout
      title="Veilige actie, van intentie tot bewijs"
      description="Engine is een local-first runtime voor begrensde, getypeerde en auditeerbare acties."
    >
      <main>
        <header className={styles.hero}>
          <div className={styles.heroGlow} aria-hidden="true" />
          <div className={styles.heroInner}>
            <div className={styles.statusRow}>
              <span className={styles.statusBadge}>
                <span aria-hidden="true" /> EXPERIMENTEEL
              </span>
              <span className={styles.version}>LOCAL-FIRST · PROVIDER-NEUTRAL</span>
            </div>
            <Heading as="h1">
              Van intentie naar actie,
              <br />
              <em>zonder de controle uit handen te geven.</em>
            </Heading>
            <p className={styles.lead}>
              Engine is een runtime voor begrensde, getypeerde en auditeerbare acties over software en
              fysieke systemen. Brains mogen voorstellen. Het Heart coördineert, valideert en boekt;
              policy bepaalt wie wat mag uitvoeren.
            </p>
            <div className={styles.heroActions}>
              <Link className={styles.primaryButton} to="/docs/concepts/wat-is-engine">
                Lees de documentatie <span aria-hidden="true">→</span>
              </Link>
              <Link className={styles.secondaryButton} href="https://github.com/proofofwork-agency/engine">
                Bekijk op GitHub
              </Link>
            </div>
            <div className={styles.principles} aria-label="Kernprincipes">
              <span>LLM voorstel ≠ autoriteit</span>
              <span>Voorspelling ≠ observatie</span>
              <span>Policy ≠ fysieke veiligheid</span>
            </div>
          </div>
        </header>

        <Architecture />
        <Lifecycle />
        <Modes />

        <section className={styles.finalCta}>
          <span className={styles.eyebrow}>Bouw met scherpe grenzen</span>
          <Heading as="h2">Ontdek de architectuur, SDK, CLI en plugincontracten.</Heading>
          <Link className={styles.primaryButton} to="/docs/concepts/wat-is-engine">
            Start bij het overzicht <span aria-hidden="true">→</span>
          </Link>
        </section>
      </main>
    </Layout>
  );
}

export default Home;
