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
    title: 'Deterministic',
    text: 'One general executive uses fixed logic. Policy preserves the same authority boundary without a model provider.',
  },
  {
    index: '02',
    title: 'Model-backed',
    text: 'One general executive uses a model for deliberation and proposals. Policy still decides whether an action is authorized.',
  },
  {
    index: '03',
    title: 'Multiple specialists',
    text: 'Zero or more specialist brains assist the general executive. They advise within scope and receive no execution rights.',
  },
];

function Architecture() {
  return (
    <section className={styles.architecture} aria-labelledby="architecture-title">
      <div className={styles.sectionIntro}>
        <span className={styles.eyebrow}>System boundaries</span>
        <Heading as="h2" id="architecture-title">
          Thinking and doing stay deliberately separate.
        </Heading>
        <p>
          Engine connects exactly one general executive—optionally assisted by specialists—to a
          deterministic execution path. No brain gets a hidden route to a target.
        </p>
      </div>

      <div className={styles.systemMap}>
        <article className={clsx(styles.systemNode, styles.brainNode)}>
          <div className={styles.nodeHeader}>
            <span className={styles.nodeCode}>GENERAL EXECUTIVE / EXACTLY ONE</span>
            <span className={styles.nodePulse} aria-hidden="true" />
          </div>
          <Heading as="h3">Proposals &amp; plans</Heading>
          <p>Deterministic logic or a model-backed brain, with optional specialists.</p>
          <span className={styles.nodeOutput}>OUTPUT · ProposedAction</span>
        </article>

        <div className={styles.policyGate} aria-label="Independent policy and authorization boundary">
          <span>SCHEMA</span>
          <strong>POLICY GATE</strong>
          <span>AUTHORIZATION</span>
        </div>

        <article className={clsx(styles.systemNode, styles.heartNode)}>
          <div className={styles.nodeHeader}>
            <span className={styles.nodeCode}>HEART / DURABLE STATE</span>
            <span className={styles.nodePulse} aria-hidden="true" />
          </div>
          <Heading as="h3">Coordination &amp; records</Heading>
          <p>Typed state, validation, lifecycle, receipts, effects, and recovery.</p>
          <span className={styles.nodeOutput}>OUTPUT · ExecutionReceipt</span>
        </article>

        <div className={styles.pluginRail}>
          <span className={styles.railLabel}>PLUGIN INTERFACE</span>
          <span>Capabilities</span>
          <span>Providers</span>
          <span>Controllers</span>
          <span>Oracles</span>
        </div>

        <div className={styles.targets} aria-label="Example targets">
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
        <span className={styles.eyebrow}>One inspectable chain</span>
        <Heading as="h2" id="lifecycle-title">
          Every mutation leaves evidence.
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
        Missing telemetry is <strong>UNKNOWN</strong>, not automatically success or failure.
      </p>
    </section>
  );
}

function Modes() {
  return (
    <section className={styles.modes} aria-labelledby="modes-title">
      <div className={styles.sectionIntro}>
        <span className={styles.eyebrow}>Composition</span>
        <Heading as="h2" id="modes-title">
          Every Heart has exactly one general executive.
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
      title="Bounded action, from intent to evidence"
      description="Engine is a local-first runtime for bounded, typed, and auditable actions."
    >
      <main>
        <header className={styles.hero}>
          <div className={styles.heroGlow} aria-hidden="true" />
          <div className={styles.heroInner}>
            <div className={styles.statusRow}>
              <span className={styles.statusBadge}>
                <span aria-hidden="true" /> EXPERIMENTAL
              </span>
              <span className={styles.version}>LOCAL-FIRST · PROVIDER-NEUTRAL</span>
            </div>
            <Heading as="h1">
              From intent to action,
              <br />
              <em>without surrendering control.</em>
            </Heading>
            <p className={styles.lead}>
              Engine is a runtime for bounded, typed, and auditable actions across software and
              physical systems. Brains may propose. The Heart coordinates, validates, and records;
              policy decides who may execute what.
            </p>
            <div className={styles.heroActions}>
              <Link className={styles.primaryButton} to="/docs/concepts/what-is-engine">
                Read the documentation <span aria-hidden="true">→</span>
              </Link>
              <Link
                className={styles.secondaryButton}
                href="https://github.com/proofofwork-agency/engine"
              >
                View on GitHub
              </Link>
            </div>
            <div className={styles.principles} aria-label="Core invariants">
              <span>LLM proposal ≠ authority</span>
              <span>Prediction ≠ observation</span>
              <span>Policy ≠ physical safety</span>
            </div>
          </div>
        </header>

        <Architecture />
        <Lifecycle />
        <Modes />

        <section className={styles.finalCta}>
          <span className={styles.eyebrow}>Build with explicit boundaries</span>
          <Heading as="h2">Explore the architecture, SDK, CLI, and plugin contracts.</Heading>
          <Link className={styles.primaryButton} to="/docs/concepts/what-is-engine">
            Start with the overview <span aria-hidden="true">→</span>
          </Link>
        </section>
      </main>
    </Layout>
  );
}

export default Home;
