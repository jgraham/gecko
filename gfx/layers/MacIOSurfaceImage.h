/* -*- Mode: C++; tab-width: 20; indent-tabs-mode: nil; c-basic-offset: 2 -*-
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

#ifndef GFX_MACIOSURFACEIMAGE_H
#define GFX_MACIOSURFACEIMAGE_H

#include "mozilla/gfx/MacIOSurface.h"
#include "gfxImageSurface.h"

namespace mozilla {

namespace layers {

class MacIOSurfaceImage : public Image {
public:
  void SetSurface(MacIOSurface* aSurface) { mSurface = aSurface; }
  MacIOSurface* GetSurface() { return mSurface; }

  gfxIntSize GetSize() {
    return gfxIntSize(mSurface->GetDevicePixelWidth(), mSurface->GetDevicePixelHeight());
  }

  virtual already_AddRefed<gfxASurface> GetAsSurface() {
    mSurface->Lock();
    size_t bytesPerRow = mSurface->GetBytesPerRow();
    size_t ioWidth = mSurface->GetDevicePixelWidth();
    size_t ioHeight = mSurface->GetDevicePixelHeight();

    unsigned char* ioData = (unsigned char*)mSurface->GetBaseAddress();

    nsRefPtr<gfxImageSurface> imgSurface =
      new gfxImageSurface(gfxIntSize(ioWidth, ioHeight), gfxImageFormatARGB32);

    for (size_t i = 0; i < ioHeight; i++) {
      memcpy(imgSurface->Data() + i * imgSurface->Stride(),
             ioData + i * bytesPerRow, ioWidth * 4);
    }

    mSurface->Unlock();

    return imgSurface.forget();
  }

  MacIOSurfaceImage() : Image(nullptr, MAC_IOSURFACE) {}

private:
  RefPtr<MacIOSurface> mSurface;
};

} // layers
} // mozilla

#endif // GFX_SHAREDTEXTUREIMAGE_H
