// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

using System.Reflection;
using Xunit;

namespace System.IO.Tests
{
    public class LegacySwitchTests
    {
        [Fact]
        public static void LegacySwitchIsHonored()
        {
            string filePath = Path.Combine(Path.GetTempPath(), Path.GetTempFileName());

            using (FileStream fileStream = File.Create(filePath))
            {
                object strategy = fileStream
                    .GetType()
                    .GetField("_strategy", BindingFlags.NonPublic | BindingFlags.Instance)
                    .GetValue(fileStream);

                Assert.DoesNotContain(strategy.GetType().FullName, "Legacy");
            }

            File.Delete(filePath);
        }
    }
}
