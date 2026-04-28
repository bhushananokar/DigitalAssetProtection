import { renderHook } from "@testing-library/react";
import { act } from "react";
import { describe, expect, it } from "vitest";
import { usePagination } from "@/lib/hooks/usePagination";

describe("usePagination", () => {
  it("computes pages and navigation flags", () => {
    const { result } = renderHook(() => usePagination(95, 20, 1));
    expect(result.current.totalPages).toBe(5);
    expect(result.current.hasPrev).toBe(false);
    expect(result.current.hasNext).toBe(true);
    expect(result.current.pageNumbers).toEqual([1, 2, 3, 4, 5]);
  });

  it("clamps page within valid bounds", () => {
    const { result } = renderHook(() => usePagination(50, 10, 1));
    act(() => result.current.goToPage(999));
    expect(result.current.currentPage).toBe(5);
    act(() => result.current.goToPage(-3));
    expect(result.current.currentPage).toBe(1);
  });
});
