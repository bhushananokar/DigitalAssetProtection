"use client";

import { useEffect, useMemo, useState } from "react";

export function usePagination(totalItems: number, itemsPerPage = 20, initialPage = 1) {
  const [currentPage, setCurrentPage] = useState(initialPage);
  const totalPages = Math.max(1, Math.ceil(totalItems / itemsPerPage));

  useEffect(() => {
    setCurrentPage(initialPage);
  }, [initialPage]);

  const goToPage = (n: number) => {
    setCurrentPage(Math.min(totalPages, Math.max(1, n)));
  };

  const pageNumbers = useMemo(() => {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }, [totalPages]);

  return {
    currentPage,
    totalPages,
    goToPage,
    nextPage: () => goToPage(currentPage + 1),
    prevPage: () => goToPage(currentPage - 1),
    hasNext: currentPage < totalPages,
    hasPrev: currentPage > 1,
    pageNumbers,
  };
}
