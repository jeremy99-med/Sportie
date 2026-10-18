const features = [
  {
    name: "Video Analyzer",
    description:
      "Review futsal footage with player tracking, top-down views, and tactical suggestions.",
    path: "video-analyzer",
  },
  {
    name: "Community Game Ranker",
    description:
      "Explore important games across the NFL, NBA, NHL, and MLB, with community voting.",
    path: "community-game-ranker",
  },
];

export default function App() {
  return (
    <main className="container py-5">
      <header className="mb-5">
        <p className="eyebrow mb-2">SPORTIE</p>
        <h1 className="display-4 fw-bold">Find your next angle on the game.</h1>
        <p className="lead text-secondary text-sp-red">
          Film analysis for teams. Game discovery for fans.
        </p>
      </header>
      <section aria-label="Sportie features" className="row g-4">
        {features.map((feature) => (
          <article className="col-12 col-lg-6" key={feature.path}>
            <div className="card h-100 border-0 shadow-sm">
              <div className="card-body p-4">
                <h2 className="h4 card-title text-sp-green">{feature.name}</h2>
                <p className="card-text text-secondary">
                  {feature.description}
                </p>
                <span className="badge text-bg-light">{feature.path}</span>
              </div>
            </div>
          </article>
        ))}
      </section>
    </main>
  );
}
