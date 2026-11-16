const logos = import.meta.glob<string>("../assets/provider-icons/*.svg", {
  eager: true,
  query: "?url",
  import: "default",
});

export default function ProviderLogo({
  provider,
  customMark = "+",
}: {
  provider: string;
  customMark?: string;
}) {
  const src = logos[`../assets/provider-icons/${provider}.svg`];
  return (
    <span
      className={`provider-mark ${src && provider !== "custom" ? "provider-logo" : ""}`}
      aria-hidden="true"
    >
      {src && provider !== "custom" ? (
        <img src={src} alt="" width="32" height="32" draggable={false} />
      ) : (
        customMark
      )}
    </span>
  );
}
