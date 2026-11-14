import type { Metadata } from "next";
import { CinematicExperience } from "@/components/cinematic/CinematicExperience";
import { Reveal } from "@/components/landing/Reveal";
import { SiteNav } from "@/components/landing/SiteNav";
import { About, Contact, Footer, Services } from "@/components/landing/ContentSections";

export const metadata: Metadata = {
  title: "PRECURSOR AI: SAR/InSAR ground-change monitoring (research prototype)",
  description:
    "Research prototype that monitors ground-surface change with satellite SAR/InSAR and environmental data, toward future landslide early prediction.",
};

export default function Home() {
  return (
    <>
      <SiteNav />
      <main id="main">
        <div id="home">
          <CinematicExperience />
        </div>
        <About />
        <Services />
        <Contact />
      </main>
      <Footer />
      <Reveal />
    </>
  );
}
