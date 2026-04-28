import { Suspense } from "react";
import { ViolationsPageClient } from "@/components/ViolationsPageClient";

export default function ViolationsPage() {
  return (
    <Suspense fallback={<div className="card animate-pulse">Loading violations...</div>}>
      <ViolationsPageClient />
    </Suspense>
  );
}
