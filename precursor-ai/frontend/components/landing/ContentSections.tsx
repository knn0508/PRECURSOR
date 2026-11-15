import { ArrowUpRight, Mail } from "lucide-react";
import Link from "next/link";
import { CAPABILITIES, statusInfo } from "./status";
import { cn } from "@/lib/utils";

function Heading({ kicker, title, id }: { kicker: string; title: string; id: string }) {
  return (
    <div className="mb-12 md:mb-16">
      <div data-rule aria-hidden className="mb-8 h-px w-full bg-line" />
      <p data-reveal className="mb-4 font-mono text-[11px] uppercase tracking-[0.3em] text-accent">
        {kicker}
      </p>
      <h2
        id={id}
        data-reveal
        className="max-w-3xl text-[clamp(1.5rem,3.4vw,2.8rem)] font-light uppercase leading-[1.1] tracking-[0.1em]"
      >
        {title}
      </h2>
    </div>
  );
}

const FACTS = [
  {
    title: "Why landslides",
    body: "Landslides are hard to anticipate, and slow ground movement can sometimes come before a slope fails. Detecting that movement early is the open problem this project explores.",
  },
  {
    title: "What InSAR measures",
    body: "Interferometric SAR compares radar passes over the same place to estimate how the surface moved along the satellite's line of sight, through cloud and in darkness. That is deformation, not risk.",
  },
  {
    title: "Any area of interest",
    body: "You define the area. The platform is not tied to one country or region.",
  },
  {
    title: "Where it stands",
    body: "Data acquisition, InSAR processing and environmental integration are built and tested on synthetic data. No real-data validation has been done. Early prediction is a research goal: no machine-learning model is implemented yet.",
  },
];

export function About() {
  return (
    <section
      id="about"
      aria-labelledby="about-title"
      className="px-6 pb-24 pt-32 md:px-16 md:pb-32"
      style={{ background: "linear-gradient(to bottom, #02040a, var(--color-canvas) 18rem)" }}
    >
      <div className="mx-auto max-w-6xl">
        <Heading id="about-title" kicker="About" title="A research prototype for watching the ground move" />
        <div className="grid gap-12 md:grid-cols-5">
          <p data-reveal className="text-lg leading-relaxed text-ink md:col-span-2">
            PRECURSOR AI brings satellite radar and environmental data together so ground-surface change can be
            monitored and studied. It is built for the NASA Space Apps Challenge{" "}
            <span className="whitespace-nowrap">&ldquo;Dancing with the SARs&rdquo;</span>.
          </p>
          <dl className="grid gap-8 sm:grid-cols-2 md:col-span-3">
            {FACTS.map((f) => (
              <div key={f.title} data-reveal className="border-l border-line pl-5">
                <dt className="mb-2 font-mono text-[11px] uppercase tracking-[0.25em] text-accent">{f.title}</dt>
                <dd className="text-sm leading-relaxed text-ink-muted">{f.body}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  );
}

export function Services() {
  return (
    <section id="services" aria-labelledby="services-title" className="bg-canvas px-6 py-24 md:px-16 md:py-32">
      <div className="mx-auto max-w-6xl">
        <Heading id="services-title" kicker="Services" title="Platform capabilities and honest status" />
        <p data-reveal className="mb-10 max-w-2xl text-sm text-ink-muted">
          The pipeline from satellite data to early prediction. Each chip states what exists today; nothing here has
          been validated on real data.
        </p>
        <ol className="grid gap-px border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
          {CAPABILITIES.map((c, i) => {
            const s = statusInfo(c.status);
            return (
              <li key={c.id} data-reveal className="flex flex-col gap-4 bg-surface p-6">
                <div className="flex items-start justify-between gap-3">
                  <span className="font-mono text-[11px] tracking-[0.25em] text-ink-muted">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span
                    className={cn(
                      "border px-2 py-0.5 text-right font-mono text-[10px] uppercase tracking-[0.12em]",
                      s.tone,
                    )}
                  >
                    {s.label}
                  </span>
                </div>
                <h3 className="text-base font-medium uppercase leading-snug tracking-[0.08em]">{c.title}</h3>
                <p className="text-sm leading-relaxed text-ink-muted">{c.body}</p>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}

const TEAM = [
  { name: "Kanan Salmanli", role: "Full Stack Developer" },
  { name: "Sema Abdullazade", role: "UI/UX Designer" },
  { name: "Intigham Shumalov", role: "Frontend Developer" },
  { name: "Farid Gahramanov", role: "AI Engineer" },
];

export function Contact() {
  return (
    <section id="contact" aria-labelledby="contact-title" className="bg-canvas px-6 py-24 md:px-16 md:py-32">
      <div className="mx-auto max-w-6xl">
        <Heading id="contact-title" kicker="Contact" title="Talk to the team" />
        <div className="grid gap-12 md:grid-cols-2">
          <div data-reveal className="space-y-6">
            <p className="text-ink-muted">
              There is no contact form. Write to us by email or follow the project links.
            </p>
            <a
              href="mailto:nexus@support.com?subject=PRECURSOR%20AI"
              className="inline-flex items-center gap-3 border border-accent/60 bg-accent/10 px-6 py-3 font-mono text-xs uppercase tracking-[0.2em] text-accent transition-colors hover:bg-accent hover:text-canvas"
            >
              <Mail aria-hidden className="h-4 w-4" />
              nexus@support.com
            </a>
            <ul className="space-y-2 font-mono text-[11px] uppercase tracking-[0.2em] text-ink-muted">
              <li>Email: placeholder address, to be replaced</li>
              <li>GitHub: placeholder, link not set yet</li>
              <li>Team page: placeholder, link not set yet</li>
            </ul>
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 font-mono text-xs uppercase tracking-[0.2em] text-ink hover:text-accent"
            >
              Open the dashboard
              <ArrowUpRight aria-hidden className="h-4 w-4" />
            </Link>
          </div>
          <div data-reveal>
            <h3 className="mb-4 font-mono text-[11px] uppercase tracking-[0.25em] text-accent">Team</h3>
            <ul className="divide-y divide-line border-y border-line">
              {TEAM.map((m) => (
                <li key={m.name} className="flex items-baseline justify-between gap-4 py-4">
                  <span className="text-base">{m.name}</span>
                  <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-muted">{m.role}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

export function Footer() {
  return (
    <footer className="border-t border-line bg-canvas px-6 py-12 md:px-16">
      <div className="mx-auto grid max-w-6xl gap-8 md:grid-cols-2">
        <div>
          <p className="text-xs font-semibold tracking-[0.25em]">PRECURSOR AI</p>
          <p className="mt-3 max-w-md text-sm text-ink-muted">
            Built for the NASA Space Apps Challenge &ldquo;Dancing with the SARs&rdquo;. An independent team project;
            not affiliated with or endorsed by NASA.
          </p>
        </div>
        <p className="text-sm leading-relaxed text-ink-muted">
          <strong className="font-medium text-ink">Research prototype.</strong> Not an operational warning system and
          not for safety or emergency decisions. Visuals on this page are illustrative, built from synthetic data.
        </p>
      </div>
    </footer>
  );
}
