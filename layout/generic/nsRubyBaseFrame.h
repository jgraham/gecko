/* -*- Mode: C++; tab-width: 2; indent-tabs-mode: nil; c-basic-offset: 2 -*- */
/* vim: set ts=2 et sw=2 tw=80: */
/* This Source Code is subject to the terms of the Mozilla Public License
 * version 2.0 (the "License"). You can obtain a copy of the License at
 * http://mozilla.org/MPL/2.0/. */

/* rendering object for CSS "display: ruby-base" */

#ifndef nsRubyBaseFrame_h___
#define nsRubyBaseFrame_h___

#include "nsRubyContentFrame.h"

typedef nsRubyContentFrame nsRubyBaseFrameSuper;

/**
 * Factory function.
 * @return a newly allocated nsRubyBaseFrame (infallible)
 */
nsContainerFrame* NS_NewRubyBaseFrame(nsIPresShell* aPresShell,
                                      nsStyleContext* aContext);

class nsRubyBaseFrame final : public nsRubyBaseFrameSuper
{
public:
  NS_DECL_FRAMEARENA_HELPERS
  NS_DECL_QUERYFRAME_TARGET(nsRubyBaseFrame)
  NS_DECL_QUERYFRAME

  // nsIFrame overrides
  virtual nsIAtom* GetType() const override;

#ifdef DEBUG_FRAME_DUMP
  virtual nsresult GetFrameName(nsAString& aResult) const override;
#endif

protected:
  friend nsContainerFrame* NS_NewRubyBaseFrame(nsIPresShell* aPresShell,
                                               nsStyleContext* aContext);
  explicit nsRubyBaseFrame(nsStyleContext* aContext)
    : nsRubyBaseFrameSuper(aContext) {}
};

#endif /* nsRubyBaseFrame_h___ */
