import SkeletonBlock from "./SkeletonBlock";


export default function LoadingSkeleton({ lines = 3, card = false }) {
  return <SkeletonBlock lines={lines} className={card ? "loading-card" : ""} />;
}
